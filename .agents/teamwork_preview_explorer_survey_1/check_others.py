import json
import os

def check_other_files():
    # industries.json
    with open('data/industries.json', 'r', encoding='utf-8') as f:
        ind = json.load(f)
    print("industries.json count:", len(ind))
    if ind:
        print("Sample industry entry:", json.dumps(ind[0], indent=2, ensure_ascii=False))

    # models_summary.txt
    with open('data/models_summary.txt', 'r', encoding='utf-8') as f:
        txt = f.read(1000)
    print("\nmodels_summary.txt snippet:\n", txt)

if __name__ == '__main__':
    check_other_files()
