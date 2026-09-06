import os
import sys
import ssl
import re
import time
import gzip
import zlib
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup, NavigableString

from services.tls_config import tls_ssl_context
import logging

logger = logging.getLogger(__name__)

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("Could not switch the console to UTF-8", exc_info=True)

# TLS policy comes from services/tls_config.py (verify ON by default,
# VNSTOCK_INSECURE_TLS=1 to opt out).
ssl_context = tls_ssl_context()

class ArticleReaderCache:
    def __init__(self):
        self._store: Dict[str, tuple[Dict[str, Any], float]] = {}

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        if url in self._store:
            data, expire_at = self._store[url]
            if time.time() < expire_at:
                return data
            else:
                del self._store[url]
        return None

    def set(self, url: str, data: Dict[str, Any], ttl_seconds: int = 3600):
        self._store[url] = (data, time.time() + ttl_seconds)

article_cache = ArticleReaderCache()

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', str(text)).strip()
    return text

def extract_article(url: str) -> Dict[str, Any]:
    """
    Fetches and cleanly extracts the full article content (Title, Sapo, Body Paragraphs, Images, Author, Date)
    from major Vietnamese news domains, inspired by VNNewsCrawler.
    """
    if not url or not url.startswith("http"):
        return {
            "status": "error",
            "message": "URL bài viết không hợp lệ."
        }

    # Check Cache first
    cached = article_cache.get(url)
    if cached:
        return cached

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate'
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ssl_context, timeout=7.0) as resp:
            raw_html = resp.read()
            final_url = resp.geturl()

            # Automatic decompression
            enc = resp.headers.get('Content-Encoding', '').lower()
            if 'gzip' in enc or raw_html.startswith(b'\x1f\x8b'):
                try:
                    raw_html = gzip.decompress(raw_html)
                except Exception:
                    logger.debug("extract_article: swallowed Exception", exc_info=True)
            elif 'deflate' in enc:
                try:
                    raw_html = zlib.decompress(raw_html)
                except Exception:
                    logger.debug("extract_article: swallowed Exception", exc_info=True)

            # Detect encoding
            charset = resp.headers.get_content_charset()
            if charset:
                try:
                    html_text = raw_html.decode(charset)
                except Exception:
                    html_text = raw_html.decode('utf-8', errors='ignore')
            else:
                try:
                    html_text = raw_html.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        html_text = raw_html.decode('windows-1258')
                    except Exception:
                        html_text = raw_html.decode('utf-8', errors='ignore')

        soup = BeautifulSoup(html_text, 'html.parser')

        # Remove noise tags
        for noise in soup.find_all(['script', 'style', 'noscript', 'iframe', 'svg', 'button', 'form', 'header', 'footer', 'nav', 'aside']):
            noise.decompose()

        parsed_domain = urllib.parse.urlparse(final_url).netloc.lower()

        title = ""
        sapo = ""
        author = ""
        published_at = ""
        paragraphs = []
        cover_image = ""
        source_name = "Báo Điện Tử"

        # 1. Extract Meta tags for fallback & exact category
        meta_title = soup.find('meta', property='og:title') or soup.find('meta', attrs={'name': 'title'})
        meta_desc = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
        meta_img = soup.find('meta', property='og:image')
        meta_author = soup.find('meta', attrs={'name': 'author'}) or soup.find('meta', property='article:author')
        meta_pub = soup.find('meta', property='article:published_time') or soup.find('meta', attrs={'name': 'pubdate'}) or soup.find('meta', property='og:updated_time')
        meta_section = soup.find('meta', property='article:section') or soup.find('meta', attrs={'name': 'category'}) or soup.find('meta', property='og:category') or soup.find('meta', attrs={'name': 'keywords'})

        section_name = ""
        if meta_section and meta_section.get('content'):
            section_name = clean_text(meta_section['content'])

        if meta_title and meta_title.get('content'):
            title = clean_text(meta_title['content'])
        if meta_desc and meta_desc.get('content'):
            sapo = clean_text(meta_desc['content'])
        if meta_img and meta_img.get('content'):
            cover_image = meta_img['content']
        if meta_author and meta_author.get('content'):
            author = clean_text(meta_author['content'])
        if meta_pub and meta_pub.get('content'):
            published_at = clean_text(meta_pub['content'])

        # 2. Domain-Specific Extraction Logic
        if "google.com" in parsed_domain:
            return {
                "status": "error",
                "message": "Đây là liên kết tổng hợp trung gian của Google Tin Tức (không chứa nội dung bài viết gốc).",
                "url": final_url
            }

        content_container = None

        if "cafef.vn" in parsed_domain:
            source_name = "CafeF"
            t_el = soup.find('h1', class_='title') or soup.find('h1', class_='title_detail_news')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('h2', class_='sapo') or soup.find('div', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('span', class_='pdate') or soup.find('span', class_='date')
            if d_el: published_at = clean_text(d_el.get_text())
            a_el = soup.find('p', class_='author') or soup.find('span', class_='author')
            if a_el: author = clean_text(a_el.get_text())
            content_container = soup.find('div', id='mainContent') or soup.find('div', class_='detail-content') or soup.find('div', class_='knc-content')

        elif "vietstock.vn" in parsed_domain:
            source_name = "Vietstock"
            t_el = soup.find('h1', class_='article-title') or soup.find('h1', class_='header-detail') or soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='header-sapo') or soup.find('div', class_='sapo') or soup.find('p', class_='sapo') or soup.find('h2', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('span', class_='date') or soup.find('div', class_='date') or soup.find('div', class_='article-date')
            if d_el: published_at = clean_text(d_el.get_text())
            content_container = soup.find('div', class_='p-content') or soup.find('div', id='vst_detail') or soup.find('div', class_='content') or soup.find('div', class_='content_detail') or soup.find('div', class_='article-content')

        elif "vneconomy.vn" in parsed_domain:
            source_name = "VnEconomy"
            t_el = soup.find('h1', class_='detail__title')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='detail__summary') or soup.find('h2', class_='detail__summary')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('div', class_='detail__meta')
            if d_el: published_at = clean_text(d_el.get_text())
            content_container = soup.find('div', class_='detail__content')

        elif "vnexpress.net" in parsed_domain:
            source_name = "VnExpress"
            t_el = soup.find('h1', class_='title-detail') or soup.find('h1', class_='title_post')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('p', class_='description')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('span', class_='date')
            if d_el: published_at = clean_text(d_el.get_text())
            a_el = soup.find('p', class_='author') or soup.find('p', class_='Normal', align='right')
            if a_el: author = clean_text(a_el.get_text())
            content_container = soup.find('article', class_='fck_detail') or soup.find('div', class_='sidebar-1')

        elif "dantri.com.vn" in parsed_domain:
            source_name = "Dân Trí"
            t_el = soup.find('h1', class_='title-page') or soup.find('h1', class_='dt-news__title')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='singular-sapo') or soup.find('h2', class_='dt-news__sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('time', class_='author-time') or soup.find('time')
            if d_el: published_at = clean_text(d_el.get_text())
            content_container = soup.find('div', class_='singular-content') or soup.find('div', class_='dt-news__content')

        elif "vietnamnet.vn" in parsed_domain:
            source_name = "VietNamNet"
            t_el = soup.find('h1', class_='content-detail-title')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='content-detail-sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('div', class_='bread-crumb-detail__time')
            if d_el: published_at = clean_text(d_el.get_text())
            content_container = soup.find('div', class_='maincontent') or soup.find('div', id='maincontent')

        elif "tinnhanhchungkhoan.vn" in parsed_domain:
            source_name = "Tin Nhanh Chứng Khoán"
            t_el = soup.find('h1', class_='article__title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='article__sapo') or soup.find('h2', class_='article__sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('div', class_='article__meta')
            if d_el: published_at = clean_text(d_el.get_text())
            content_container = soup.find('div', class_='article__body')

        elif "baodautu.vn" in parsed_domain:
            source_name = "Báo Đầu Tư"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo') or soup.find('h2', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='content') or soup.find('div', id='content')

        elif "cafebiz.vn" in parsed_domain:
            source_name = "CafeBiz"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='detail-content') or soup.find('div', class_='content')

        elif "tuoitre.vn" in parsed_domain:
            source_name = "Tuổi Trẻ"
            t_el = soup.find('h1', class_='article-title') or soup.find('h1', class_='detail-title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('h2', class_='detail-sapo') or soup.find('h2', class_='sapo') or soup.find('div', class_='detail-sapo') or soup.find('h2', class_='article-sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('div', class_='date-time') or soup.find('div', class_='detail-time')
            if d_el: published_at = clean_text(d_el.get_text())
            a_el = soup.find('div', class_='author-info') or soup.find('div', class_='author')
            if a_el: author = clean_text(a_el.get_text())
            content_container = soup.find('div', attrs={'itemprop': 'articleBody'}) or soup.find('div', class_='detail-cmain') or soup.find('div', class_='detail-content')

        elif "thanhnien.vn" in parsed_domain:
            source_name = "Thanh Niên"
            t_el = soup.find('h1', class_='detail-title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='detail-sapo') or soup.find('h2', class_='detail-sapo') or soup.find('div', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('div', class_='detail-time') or soup.find('span', class_='time')
            if d_el: published_at = clean_text(d_el.get_text())
            content_container = soup.find('div', attrs={'itemprop': 'articleBody'}) or soup.find('div', class_='detail-content') or soup.find('div', class_='detail-cmain') or soup.find('div', class_='cms-body')

        elif "vietnambiz.vn" in parsed_domain:
            source_name = "VietnamBiz"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo') or soup.find('h2', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='content-detail') or soup.find('div', class_='content')

        elif "znews.vn" in parsed_domain:
            source_name = "Znews"
            t_el = soup.find('h1', class_='the-article-title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('p', class_='the-article-summary')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='the-article-body') or soup.find('div', class_='the-article-content')

        elif "tienphong.vn" in parsed_domain:
            source_name = "Tiền Phong"
            t_el = soup.find('h1', class_='article__title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='article__sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='article__body') or soup.find('div', class_='content')

        elif "nld.com.vn" in parsed_domain:
            source_name = "Người Lao Động"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='content-news-detail') or soup.find('div', class_='content')

        elif "bnews.vn" in parsed_domain:
            source_name = "BNEWS"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo') or soup.find('h2', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='content-detail') or soup.find('div', class_='post-content') or soup.find('div', class_='content')

        elif "laodong.vn" in parsed_domain:
            source_name = "Lao Động"
            t_el = soup.find('h1', class_='title') or soup.find('h1', class_='article-title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('p', class_='sapo') or soup.find('div', class_='sapo') or soup.find('h2', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            d_el = soup.find('span', class_='time') or soup.find('div', class_='time')
            if d_el: published_at = clean_text(d_el.get_text())
            a_el = soup.find('div', class_='author') or soup.find('p', class_='author')
            if a_el: author = clean_text(a_el.get_text())
            content_container = soup.find('div', class_='article-content') or soup.find('div', attrs={'itemprop': 'articleBody'}) or soup.find('div', class_='content')

        elif "nhandan.vn" in parsed_domain:
            source_name = "Nhân Dân"
            t_el = soup.find('h1', class_='article-title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='article-sapo') or soup.find('div', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='detail-content') or soup.find('div', class_='content') or soup.find('div', class_='entry-content')

        elif "congthuong.vn" in parsed_domain:
            source_name = "Công Thương"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo') or soup.find('h2', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='detail-content') or soup.find('div', class_='content') or soup.find('div', class_='entry-content')

        elif "taichinhdoanhnghiep.vn" in parsed_domain:
            source_name = "Tài Chính Doanh Nghiệp"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='detail-content') or soup.find('div', class_='post-content') or soup.find('div', class_='content')

        elif "markettimes.vn" in parsed_domain:
            source_name = "MarketTimes"
            t_el = soup.find('h1', class_='title') or soup.find('h1')
            if t_el: title = clean_text(t_el.get_text())
            s_el = soup.find('div', class_='sapo')
            if s_el: sapo = clean_text(s_el.get_text())
            content_container = soup.find('div', class_='detail-content') or soup.find('div', class_='post-content') or soup.find('div', class_='content')

        # Fallback to generic article container
        if not content_container:
            content_container = (
                soup.find('article') or 
                soup.find('div', attrs={'itemprop': 'articleBody'}) or
                soup.find('div', class_=re.compile(r'content|article|detail|entry-content|post-body', re.I)) or
                soup.find('main') or
                soup.body
            )

        # Fallback Title if still empty
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = clean_text(h1.get_text())
            elif soup.title:
                title = clean_text(soup.title.get_text())

        title = re.sub(r'\s*[\-|–|\|]\s*(CafeF|Vietstock|VnEconomy|VnExpress|Dân trí|VietNamNet|Báo Đầu tư|CafeBiz|Tuổi Trẻ|Thanh Niên|Znews|BNEWS).*$', '', title, flags=re.IGNORECASE).strip()

        # Extract structured paragraphs and inline figures/images
        if content_container:
            for sub_noise in content_container.find_all(['div', 'aside', 'section'], class_=re.compile(r'related|box-relate|ad-|adv|banner|share|social|tags|widget|recommend|embed|author-info', re.I)):
                sub_noise.decompose()

            p_tags = content_container.find_all(['p', 'blockquote', 'figure', 'h2', 'h3'])
            for p in p_tags:
                tag_name = p.name.lower()
                
                # Check for figure/image
                if tag_name == 'figure':
                    img = p.find('img')
                    if img and (img.get('src') or img.get('data-src')):
                        src = img.get('data-src') or img.get('src')
                        if src and not src.startswith('data:'):
                            cap_tag = p.find('figcaption') or p.find('p')
                            cap_text = clean_text(cap_tag.get_text()) if cap_tag else ""
                            paragraphs.append({
                                "type": "image",
                                "src": src,
                                "caption": cap_text,
                                "text": cap_text
                            })
                    continue

                txt = clean_text(p.get_text())
                if not txt or len(txt) < 10:
                    continue

                if any(skip_kw in txt.lower() for skip_kw in [
                    'tin liên quan:', 'bài viết liên quan', 'xem thêm:', 'đọc thêm:', 
                    'theo dõi chúng tôi trên', 'tải app', 'bản quyền thuộc về', 'dòng sự kiện:'
                ]):
                    continue

                if sapo and txt.startswith(sapo[:30]):
                    continue

                if tag_name in ['h2', 'h3']:
                    paragraphs.append({
                        "type": "heading",
                        "text": txt
                    })
                elif tag_name == 'blockquote':
                    paragraphs.append({
                        "type": "quote",
                        "text": txt
                    })
                else:
                    paragraphs.append({
                        "type": "paragraph",
                        "text": txt
                    })

        # Universal fallback: If fewer than 2 paragraphs found, search all body paragraphs
        if len(paragraphs) < 2 and soup.body:
            for p in soup.body.find_all('p'):
                txt = clean_text(p.get_text())
                if len(txt) > 35 and not any(skip in txt.lower() for skip in ['liên hệ', 'quảng cáo', 'tòa soạn', 'hotline', 'copyright', 'bản quyền', 'cookie', 'theo dõi']):
                    if not any(existing.get('text') == txt for existing in paragraphs):
                        paragraphs.append({"type": "paragraph", "text": txt})

        if not paragraphs:
            if sapo:
                paragraphs.append({"type": "paragraph", "text": sapo})
            paragraphs.append({
                "type": "paragraph",
                "text": "Nội dung bài viết có định dạng đặc thù từ nguồn báo gốc. Quý độc giả có thể bấm 'Đọc bài gốc trên báo ↗' bên dưới để xem chi tiết."
            })

        # Format published_at cleanly
        if published_at:
            published_at = re.sub(r'\s+', ' ', published_at).strip()
            # If ISO string e.g. 2026-08-18T12:00:00, format simply
            if "T" in published_at and len(published_at) >= 19:
                published_at = published_at[:10] + ' ' + published_at[11:16]

        result = {
            "status": "success",
            "url": final_url,
            "domain": parsed_domain,
            "source": source_name,
            "section": section_name,
            "title": title,
            "sapo": sapo,
            "published_at": published_at or "Cập nhật gần đây",
            "author": author,
            "cover_image": cover_image,
            "paragraphs": paragraphs,
            "paragraph_count": len(paragraphs)
        }

        article_cache.set(url, result, ttl_seconds=3600)
        return result

    except Exception as e:
        return {
            "status": "error",
            "message": f"Không thể tải bài viết: {str(e)}",
            "url": url
        }
