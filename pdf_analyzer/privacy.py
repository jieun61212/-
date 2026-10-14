"""Automatically remove source identities from analysis and manuscript outputs."""
import hashlib
import re

ROLE = r'(?:원\s*고|피\s*고(?:\s*인)?|신청인|채무자|채권자|고소인|피해자|성명|이름|대표자|증인)'
EXCLUDED = {'주장', '청구', '신청', '대리인', '소송', '주문', '또는', '대하여', '에게', '사이에', '사건', '법원', '주식회사'}


def normalize(value):
    return re.sub(r'[\s\-.,:()（）]', '', value)


def source_names(text):
    names = set()
    pattern = ROLE + r'[ \t]*[:：]?[ \t]*([가-힣]{2,4}?)(?=[ \t\n,.(（]|은|는|이[ \t]|가[ \t]|의|을|를|에게|$)'
    for match in re.finditer(pattern, text):
        name = match.group(1)
        if name not in EXCLUDED:
            names.add(name)
    spaced = ROLE + r'[ \t]*[:：]?[ \t]*([가-힣](?:[ \t]+[가-힣]){1,3})(?=[ \t]*\n|$)'
    for match in re.finditer(spaced, text):
        names.add(normalize(match.group(1)))
    return names


def fingerprints(text):
    # Keep irreversible hashes, never raw party names, in history.
    return [{'length': len(name), 'sha256': hashlib.sha256(name.encode()).hexdigest()} for name in sorted(source_names(text))]


def remove_identities(text, identities):
    # Match spaced variants too, without retaining names between requests.
    chars = [(index, character) for index, character in enumerate(text) if normalize(character)]
    normalized = ''.join(character for _, character in chars)
    ranges = []
    for item in identities:
        length = item['length']
        for start in range(max(0, len(normalized) - length + 1)):
            if hashlib.sha256(normalized[start:start+length].encode()).hexdigest() == item['sha256']:
                ranges.append((chars[start][0], chars[start+length-1][0]+1))
    merged = []
    for start, end in sorted(set(ranges)):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        text = text[:start] + '[당사자]' + text[end:]
    return text


def clean_output(text, identities=(), allowed_phone=None):
    from pdf_analyzer.analyzer import anonymize
    # Preserve the registered public contact, while removing private phone numbers.
    placeholder = '등록법인연락처보존표식'
    if allowed_phone:
        text = text.replace(allowed_phone, placeholder)
    text = remove_identities(text, [*identities, *fingerprints(text)])
    if allowed_phone:
        text = text.replace('연락처: ' + placeholder, '문의 번호: ' + placeholder)
    text = anonymize(text, remove_names=False)
    text = text.replace('문의 번호: ' + placeholder, '연락처: ' + placeholder)
    if allowed_phone:
        text = text.replace(placeholder, allowed_phone)
    return text


def clean_structure(value, identities=(), allowed_phone=None):
    if isinstance(value, str):
        return clean_output(value, identities, allowed_phone)
    if isinstance(value, list):
        return [clean_structure(v, identities, allowed_phone) for v in value]
    if isinstance(value, dict):
        return {k: clean_structure(v, identities, allowed_phone) for k, v in value.items()}
    return value
