"""Fail if any file that git would commit contains an API key. Prints only file:line, never the secret."""
import re, subprocess, sys

PATTERNS = [re.compile(p) for p in (r"fw_[A-Za-z0-9]{20,}", r"sk-ant-[A-Za-z0-9_\-]{20,}", r"sk-proj-[A-Za-z0-9_\-]{20,}",
                                    r"hf_[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}")]


def files():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if f]


def main():
    hits = []
    for f in files():
        if f == ".env" or f.endswith(".env"):
            hits.append(f"{f}: env file would be committed")
            continue
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for n, line in enumerate(fh, 1):
                    if any(p.search(line) for p in PATTERNS):
                        hits.append(f"{f}:{n}")
        except (IsADirectoryError, FileNotFoundError):
            continue
    if hits:
        print("Possible secrets found (values not shown):\n" + "\n".join(hits))
        sys.exit(1)
    print(f"No secrets found in {len(files())} files.")


if __name__ == "__main__":
    main()
