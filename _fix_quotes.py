"""Fix smart quotes in node.py - replace Chinese curly quotes with ASCII."""
path = r'D:\GameDownload\Enterprise-Automation-Agent\agent\src\core\node.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

left = content.count('“')
right = content.count('”')
print(f'Left smart quotes: {left}, Right smart quotes: {right}')

content = content.replace('“', '"').replace('”', '"')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Replacement done')
