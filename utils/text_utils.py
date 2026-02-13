"""Text processing utilities."""
import re
import chardet


def detect_encoding(file_path):
    """Detect file encoding."""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    result = chardet.detect(raw_data)
    return result['encoding']


def read_text_file(file_path):
    """Read text file with automatic encoding detection."""
    encoding = detect_encoding(file_path)
    with open(file_path, 'r', encoding=encoding) as f:
        content = f.read()

    # Remove BOM if present
    if content.startswith('\ufeff'):
        content = content[1:]

    return content


def normalize_punctuation(text):
    """Normalize full-width and half-width punctuation."""
    replacements = {
        '，': ',',
        '。': '.',
        '！': '!',
        '？': '?',
        '；': ';',
        '：': ':',
        '"': '"',
        '"': '"',
        ''': "'",
        ''': "'",
        '（': '(',
        '）': ')',
        '【': '[',
        '】': ']',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def clean_text(text):
    """Clean and normalize text."""
    # Remove multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def find_sentence_end(text, start_pos):
    """Find the nearest sentence-ending punctuation after start_pos."""
    sentence_ends = ['.', '!', '?', '。', '！', '？']

    min_pos = len(text)
    for punct in sentence_ends:
        pos = text.find(punct, start_pos)
        if pos != -1 and pos < min_pos:
            min_pos = pos

    if min_pos == len(text):
        return start_pos

    return min_pos + 1


def extract_text_snippet(text, length=30):
    """Extract a snippet of text for display."""
    if len(text) <= length:
        return text
    return text[:length] + "..."


def count_chinese_chars(text):
    """Count Chinese characters in text."""
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def split_by_sentence(text, max_length=100):
    """Split text into sentences."""
    # Chinese sentence endings
    pattern = r'[.!?。！？]+'
    sentences = re.split(pattern, text)

    result = []
    for sent in sentences:
        sent = sent.strip()
        if sent:
            result.append(sent)

    return result


def get_text_markers(text, marker_length=30):
    """Get start and end markers from text."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    if not lines:
        return "", ""

    # Find first substantial line
    start_marker = ""
    for line in lines:
        if len(line) >= 15:
            start_marker = line[:marker_length]
            break

    # Find last substantial line
    end_marker = ""
    for line in reversed(lines):
        if len(line) >= 15:
            end_marker = line[-marker_length:]
            break

    return start_marker, end_marker
