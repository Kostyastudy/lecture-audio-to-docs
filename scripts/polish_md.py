"""Light cleanup for Chinese Markdown before building the DOCX.

- pairs ASCII double quotes into Chinese curly quotes
- drops meaningless short parentheticals such as （哎）（就是说）
- removes spaces between Chinese characters and normalizes full-width brackets

Usage:
  python polish_md.py C:\\Voice\\work\\transcript.md C:\\Voice\\work\\summary.md
"""
import argparse
import re

STOP = set("就的是在把要会可和都也还而被让用对与或等他我你这那其之以于上下里中为有很更再又才只但而且例如如说想去做来个么呢吧啊嗯呃")


def strip_parens(text):
    def repl(m):
        inner = m.group(1)
        core = inner.strip("…· ,，。、")
        if 0 < len(core) <= 3 and all(ch in STOP for ch in core):
            return ""
        return m.group(0)
    return re.sub(r"（([^（）]{1,3})）", repl, text)


def fix_quotes(text):
    out = []
    for line in text.split("\n"):
        buf = []
        open_q = True
        for ch in line:
            if ch == '"':
                buf.append("“" if open_q else "”")
                open_q = not open_q
            else:
                buf.append(ch)
        out.append("".join(buf))
    return "\n".join(out)


def tidy_space(text):
    text = re.sub(r"[ \t]+(?=[\u4e00-\u9fff])", "", text)
    text = text.replace("（ ", "（").replace(" ）", "）")
    text = re.sub(r"…{3,}", "……", text)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--keep-parens", action="store_true")
    args = ap.parse_args()
    for path in args.paths:
        s = open(path, encoding="utf-8").read()
        if not args.keep_parens:
            s = strip_parens(s)
        s = fix_quotes(s)
        s = tidy_space(s)
        open(path, "w", encoding="utf-8").write(s)
        print("polished", path, len(s))


if __name__ == "__main__":
    main()
