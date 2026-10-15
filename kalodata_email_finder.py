#!/usr/bin/env python3
"""
=============================================================================
KALODATA TIKTOK CREATOR EMAIL FINDER (CHOCODATA ONLY)
=============================================================================
- Semua pencarian LANGSUNG lewat API Chocodata (tanpa scrape lokal, tanpa cloud lain).
- Filter Barter: Gmail/iCloud/Outlook/Yahoo dll vs Agensi (Paid).
- Output CSV rapi untuk Excel + TXT.
- Catatan: setiap username = 1 request ke Chocodata (memakai kredit).
=============================================================================
"""

import os
import re
import csv
import json
import time
import ssl
import random
import argparse
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Tuple

# Chocodata API
CHOCO_API_URL = "https://api.chocodata.com/api/v1/tiktok/email"
# API key wajib diberikan lewat environment variable atau web form.
CHOCO_API_KEY = os.environ.get("CHOCODATA_API_KEY", "").strip()
CHOCO_COUNTRY = "us"

try:
    SSL_CTX = ssl._create_unverified_context()
except Exception:
    SSL_CTX = ssl.create_default_context()
    SSL_CTX.check_hostname = False
    SSL_CTX.verify_mode = ssl.CERT_NONE

BARTER_DOMAINS = {
    'gmail.com', 'googlemail.com',
    'icloud.com', 'me.com', 'mac.com',
    'yahoo.com', 'ymail.com', 'rocketmail.com', 'yahoo.co.id', 'yahoo.co.uk',
    'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
    'aol.com',
    'proton.me', 'protonmail.com',
    'zoho.com',
    'mail.com', 'gmx.com', 'gmx.net',
    'yandex.com'
}

AGENCY_KEYWORDS = [
    'talent', 'mgmt', 'management', 'agency', 'entertainment', 'collab', 'media',
    'creators', 'influencer', 'press', 'rep', 'team', 'pr', 'society'
]

KNOWN_AGENCY_DOMAINS = {
    'nowadaystalent.com', 'starlinemgmt.com', 'unitedtalent.com', 'wmeagency.com',
    'caa.com', 'a-listme.com', 'lindenentertainment.com', 'collxab.com',
    'tacticasociety.com', 'eyelightscreative.com', 'viralnation.com', 'nightmedia.co',
    'select.co', 'thesociablesociety.com', 'palettemgmt.com', 'talentxent.com',
    'shine-talent.com', 'scalemanagement.co', 'infinitetalent.co', 'clovertalent.com'
}

IGNORED_DOMAINS = {
    'tiktok.com', 'bytedance.com', 'sentry.io', 'example.com',
    'test.com', 'domain.com', 'wixpress.com', 'cloudflare.com',
    'akamai.com', 'schema.org', 'google.com', 'apple.com', 'youtube.com',
    'chocodata.com'
}

IGNORED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.mp4', '.css', '.js')

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE)


def classify_email(email: str) -> Tuple[str, bool]:
    if not email:
        return ("Tidak Ada", False)
    lower = email.lower().strip()
    parts = lower.split('@')
    if len(parts) != 2:
        return ("Invalid", False)
    local_part, domain = parts

    if domain in BARTER_DOMAINS:
        return ("Personal Inbox (Barter-Friendly)", True)

    if (domain in KNOWN_AGENCY_DOMAINS or
            any(k in domain for k in AGENCY_KEYWORDS) or
            any(k in local_part for k in ['mgmt', 'agency', 'talent', 'agent'])):
        return ("Agency / Management (Paid Only)", False)

    return ("Custom Domain (Review)", False)


def clean_username(raw: str) -> str:
    if not raw:
        return ""
    u = str(raw).strip()
    u = re.sub(r'[\u200B-\u200D\uFEFF\u00A0]', '', u).strip()
    u = re.sub(r'^https?://', '', u, flags=re.IGNORECASE)
    u = re.sub(r'^(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/', '', u, flags=re.IGNORECASE)
    u = u.lstrip('/@')
    u = re.split(r'[?#/]', u)[0].strip().lower()
    return u


def extract_emails(text: str) -> List[str]:
    if not text:
        return []
    valid = []
    for m in EMAIL_REGEX.findall(text):
        e = m.lower().strip()
        if any(e.endswith(ext) for ext in IGNORED_EXTENSIONS):
            continue
        parts = e.split('@')
        if len(parts) != 2:
            continue
        domain = parts[1]
        if domain in IGNORED_DOMAINS or len(parts[0]) < 1 or len(domain) < 3:
            continue
        if e not in valid:
            valid.append(e)
    return valid


def fetch_from_chocodata(username: str, api_key: Optional[str] = None) -> Tuple[Optional[str], str]:
    """
    Panggil Chocodata. Return (email, status) dengan status:
    found / not_found / auth_error / rate_limited / error
    """
    api_key = (api_key or CHOCO_API_KEY).strip()
    if not api_key:
        return (None, "auth_error")

    params = urllib.parse.urlencode({
        "api_key": api_key,
        "username": username,
        "url": f"https://www.tiktok.com/@{username}",
        "country": CHOCO_COUNTRY,
    })
    url = f"{CHOCO_API_URL}?{params}"
    last_status = "error"

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            # Parser toleran: cari email di mana pun dalam JSON
            emails = extract_emails(json.dumps(data))
            if emails:
                return (emails[0], "found")
            return (None, "not_found")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                last_status = "rate_limited"
                time.sleep(2 + attempt * 2 + random.random())
                continue
            if e.code in (401, 403):
                return (None, "auth_error")
            if e.code == 404:
                return (None, "not_found")
            last_status = f"http_{e.code}"
            time.sleep(1)
        except Exception:
            last_status = "error"
            time.sleep(1)
    return (None, last_status)


def scrape_creator(username: str, barter_only: bool = False, api_key: Optional[str] = None) -> Dict[str, Any]:
    clean_u = clean_username(username)
    if not clean_u:
        return {"username": username, "email": None, "source": None,
                "inbox_type": "Invalid", "is_barter": False, "status": "invalid"}

    email, status = fetch_from_chocodata(clean_u, api_key=api_key)

    if email:
        inbox_label, is_barter = classify_email(email)
        if barter_only and not is_barter:
            return {"username": clean_u, "email": None, "source": None,
                    "inbox_type": inbox_label, "is_barter": False,
                    "status": "skipped_agency",
                    "details": f"Email Agensi/Paid ({email}) dilewati untuk Barter"}
        return {"username": clean_u, "email": email, "source": "chocodata",
                "inbox_type": inbox_label, "is_barter": is_barter, "status": "found"}

    return {"username": clean_u, "email": None, "source": None,
            "inbox_type": "Tidak Ada", "is_barter": False, "status": status}


def detect_username_column(headers: List[str]) -> int:
    for idx, h in enumerate(headers):
        clean_h = h.lower().replace(" ", "").replace("_", "")
        if any(key in clean_h for key in [
            "creatorusername", "tiktokusername", "username", "creatorhandle",
            "handle", "account", "tiktokaccount", "creator"
        ]):
            return idx
    return 0


def run_batch_scrape(targets: List[str], workers: int = 5, barter_only: bool = False,
                     api_key: Optional[str] = None, progress_callback=None) -> List[Dict[str, Any]]:
    total = len(targets)
    mode_str = "HANYA BARTER (Gmail/iCloud/Outlook/Yahoo)" if barter_only else "SEMUA EMAIL (Termasuk Agensi)"
    print(f"\n🚀 Memulai pencarian via Chocodata untuk {total} kreator...")
    print(f"🎯 Mode: {mode_str}")
    print(f"{'No.':<4} | {'TikTok Username':<22} | {'Email Address':<36} | {'Tipe Inbox'}")
    print("-" * 88)

    results_map: Dict[int, Dict[str, Any]] = {}
    done_count = 0
    found_count = 0
    auth_warned = False

    with ThreadPoolExecutor(max_workers=workers) as executor:
        def scrape_with_progress(username):
            if progress_callback:
                progress_callback("start", username, done_count, total, None)
            return scrape_creator(username, barter_only, api_key)

        future_to_idx = {
            executor.submit(scrape_with_progress, u): idx for idx, u in enumerate(targets)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                res = future.result()
            except Exception:
                res = {"username": targets[idx], "email": None, "source": None,
                       "inbox_type": "Error", "is_barter": False, "status": "error"}

            results_map[idx] = res
            done_count += 1
            if progress_callback:
                progress_callback("done", targets[idx], done_count, total, res)

            email_str = res["email"] if res["email"] else "Not Found"
            if res["email"]:
                found_count += 1
                type_badge = "✓ Barter" if res.get("is_barter") else "• Agency/Paid"
            else:
                type_badge = f"- ({res.get('status')})"

            print(f"{done_count:<4} | {res['username']:<22} | {email_str:<36} | {type_badge}")

            if res.get("status") == "auth_error" and not auth_warned:
                auth_warned = True
                print("⚠️  API key ditolak (401/403). Cek key atau sisa kredit Chocodata.")

            time.sleep(0.2 + random.random() * 0.2)

    ordered = [results_map[i] for i in range(total)]
    pct = (found_count / total * 100) if total else 0

    print("\n" + "=" * 88)
    print(f"✓ Selesai batch ini: {found_count}/{total} email ditemukan ({pct:.1f}%)")
    print("=" * 88)
    return ordered


def save_to_excel_csv(filepath: str, results: List[Dict[str, Any]]):
    with open(filepath, mode='w', encoding='utf-8-sig', newline='') as f:
        f.write("sep=,\n")
        writer = csv.writer(f, delimiter=',')
        writer.writerow(["TikTok Username", "Email Address", "Tipe Email (Barter / Agency)", "Source", "Status"])
        for r in results:
            writer.writerow([
                r["username"],
                r["email"] or "",
                r.get("inbox_type") or "",
                r.get("source") or "",
                r.get("status") or ""
            ])


def main():
    parser = argparse.ArgumentParser(description="TikTok Creator Email Finder (Chocodata Only)")
    parser.add_argument("input_target", nargs="?", help="Username tunggal")
    parser.add_argument("-o", "--output", default="hasil_email_excel.csv", help="File output CSV")
    parser.add_argument("-t", "--txt", default="hasil_email_kalodata.txt", help="File output TXT")
    parser.add_argument("-w", "--workers", type=int, default=5, help="Jumlah worker paralel (default: 5)")
    parser.add_argument("--barter", action="store_true", help="Hanya simpan email ramah barter")
    args = parser.parse_args()

    # Cek 1 akun via command line
    if args.input_target and not os.path.exists(args.input_target):
        clean_u = clean_username(args.input_target)
        print(f"\n🔍 Mencari email untuk: @{clean_u} (via Chocodata)...")
        res = scrape_creator(clean_u, barter_only=args.barter)
        email_out = res["email"] if res["email"] else "Not Found"
        print(f"\n➡️  Hasil: {res['username']} | {email_out}")
        print(f"    Status     : {res.get('status')}")
        print(f"    Tipe Inbox : {res.get('inbox_type')}")
        print(f"    Cocok Barter: {'YA (Direct Inbox)' if res.get('is_barter') else 'TIDAK (Agency/Paid/None)'}")
        print()
        return

    all_results: List[Dict[str, Any]] = []
    seen_usernames = set()
    barter_mode = args.barter

    if not args.input_target:
        print("\n" + "=" * 76)
        print("  TIKTOK CREATOR EMAIL FINDER (CHOCODATA ONLY)")
        print("=" * 76)
        print("Pilih Mode Email:")
        print("  [1] HANYA EMAIL BARTER (Gmail, iCloud, Outlook, Yahoo - Lewati Agensi Paid)")
        print("  [2] SEMUA EMAIL (Termasuk Agensi / Paid Management)")
        print("-" * 76)
        mode_input = input("Pilihan Mode (1 atau 2, default: 1): ").strip()
        barter_mode = (mode_input != "2")

    while True:
        if not all_results:
            print("\n" + "-" * 76)
            print("Pilih cara input:")
            print("  [1] Paste username di sini (bisa copy 1 kolom dari Excel)")
            print("  [2] Baca dari file CSV Kalodata di folder ini")
            print("-" * 76)
            choice = input("Pilihan input (1 atau 2, default: 1): ").strip()
        else:
            print("\n" + "=" * 76)
            found_so_far = sum(1 for r in all_results if r["email"])
            print(f"📊 DATA TERSIMPAN: {len(all_results)} kreator | {found_so_far} email ditemukan")
            print("=" * 76)
            print("Pilihan:")
            print("  [1] Simpan Semua Data Sekarang (Format Excel Rapi)")
            print("  [2] Lanjut Cari Email Lagi (Tambah daftar username baru)")
            print("-" * 76)
            action = input("Pilihan Anda (1 atau 2, default: 1): ").strip()
            if action in ["", "1"]:
                break
            choice = "1"

        new_targets = []
        if choice == "2":
            csv_files = [f for f in os.listdir('.') if f.endswith('.csv') and not f.startswith('hasil_')]
            if csv_files:
                print(f"\nFile CSV terdeteksi: {csv_files[0]}")
                fname = csv_files[0]
            else:
                fname = input("Masukkan nama file CSV Kalodata Anda: ").strip()

            if os.path.exists(fname):
                with open(fname, mode='r', encoding='utf-8-sig', errors='ignore') as f:
                    rows = list(csv.reader(f))
                    if rows:
                        col_idx = detect_username_column(rows[0])
                        for r in rows[1:]:
                            if len(r) > col_idx and r[col_idx].strip():
                                u = clean_username(r[col_idx].strip())
                                if u and u not in seen_usernames and u not in new_targets:
                                    new_targets.append(u)
            else:
                print(f"[!] File '{fname}' tidak ditemukan!")
                continue
        else:
            print("\n📋 Silakan PASTE daftar username TikTok di bawah ini.")
            print("   (Bisa copy satu kolom dari Excel lalu Paste di sini)")
            print("   (Jika sudah selesai paste, tekan ENTER 2 KALI):")
            print("-" * 50)
            pasted_lines = []
            while True:
                try:
                    line = input()
                    if not line:
                        break
                    pasted_lines.append(line.strip())
                except EOFError:
                    break

            for l in pasted_lines:
                for p in l.replace('\t', ',').split(','):
                    clean = clean_username(p)
                    if clean and clean not in seen_usernames and clean not in new_targets:
                        new_targets.append(clean)

        if not new_targets:
            print("[!] Tidak ada username baru yang dimasukkan.")
            if not all_results:
                return
            continue

        res = run_batch_scrape(new_targets, workers=args.workers, barter_only=barter_mode)
        for r in res:
            all_results.append(r)
            seen_usernames.add(r['username'].lower())

    if not all_results:
        print("[!] Tidak ada data untuk disimpan.")
        return

    save_to_excel_csv(args.output, all_results)

    with open(args.txt, mode='w', encoding='utf-8') as f:
        for r in all_results:
            f.write(f"{r['username']} | {r['email'] if r['email'] else 'Not Found'}\n")

    found_final = sum(1 for r in all_results if r["email"])
    pct_final = (found_final / len(all_results) * 100) if all_results else 0

    print("\n" + "=" * 80)
    print("🎉 SELURUH DATA BERHASIL DISIMPAN!")
    print(f"   • Total Kreator Terekstrak : {len(all_results)}")
    print(f"   • Total Email Ditemukan    : {found_final} ({pct_final:.1f}%)")
    print(f"   • File Excel CSV Rapi      : {os.path.abspath(args.output)}")
    print(f"   • File TXT (Pipe)          : {os.path.abspath(args.txt)}")
    print("=" * 80)

    print("\nTekan Enter untuk keluar...")
    try:
        input()
    except Exception:
        pass


if __name__ == "__main__":
    main()
