import re

file_path = '/home/acer/Downloads/AuraCore/frontend/app/globals.css'
with open(file_path, 'r') as f:
    css = f.read()

# 1. Update hero-panel
css = re.sub(
    r'\.hero-panel\s*\{.*?background:\s*radial-gradient.*?linear-gradient.*?\n\}',
    r'''.hero-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(99, 102, 241, 0.15), transparent 26%),
    linear-gradient(135deg, rgba(18, 18, 21, 0.6), rgba(24, 24, 27, 0.7));
  backdrop-filter: blur(28px);
  border: 1px solid rgba(82, 82, 91, 0.4);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}''',
    css, flags=re.DOTALL
)

# 2. Update memory-planner-card
css = re.sub(
    r'\.memory-planner-card\s*\{[^}]*\}',
    r'''.memory-planner-card {
  background:
    radial-gradient(circle at top left, rgba(79, 70, 229, 0.1), transparent 40%),
    linear-gradient(180deg, rgba(20, 20, 23, 0.7), rgba(12, 12, 14, 0.8));
  backdrop-filter: blur(20px);
  border: 1px solid rgba(82, 82, 91, 0.35);
  border-radius: 24px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}''',
    css, flags=re.DOTALL
)

# 3. Update memory-score-card
css = re.sub(
    r'\.memory-score-card\s*\{.*?radial-gradient.*?linear-gradient.*?\n\}',
    r'''.memory-score-card {
  background:
    radial-gradient(circle at top center, rgba(79, 70, 229, 0.12), transparent 40%),
    linear-gradient(180deg, rgba(20, 20, 23, 0.7), rgba(12, 12, 14, 0.8));
  backdrop-filter: blur(20px);
  border: 1px solid rgba(82, 82, 91, 0.35);
  border-radius: 24px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}''',
    css, flags=re.DOTALL
)

# 4. Soften neon colors in memory-signal-card
css = re.sub(
    r'\.memory-signal-card-emerald strong\s*\{\s*color:\s*#4ade80;\s*\}',
    r'.memory-signal-card-emerald strong { color: #6ee7b7; text-shadow: 0 0 12px rgba(16, 185, 129, 0.3); }',
    css, flags=re.DOTALL
)
css = re.sub(
    r'\.memory-signal-card-amber strong\s*\{\s*color:\s*#fbbf24;\s*\}',
    r'.memory-signal-card-amber strong { color: #fcd34d; text-shadow: 0 0 12px rgba(245, 158, 11, 0.3); }',
    css, flags=re.DOTALL
)
css = re.sub(
    r'\.memory-signal-card-indigo strong\s*\{\s*color:\s*#a5b4fc;\s*\}',
    r'.memory-signal-card-indigo strong { color: #c7d2fe; text-shadow: 0 0 12px rgba(99, 102, 241, 0.4); }',
    css, flags=re.DOTALL
)

# 5. Fix .detail-card-active to not be a solid purple block
css = re.sub(
    r'\.detail-card-active\s*\{[^}]*\}',
    r'''.detail-card-active {
  border-color: rgba(99, 102, 241, 0.6);
  background: linear-gradient(145deg, rgba(79, 70, 229, 0.15), rgba(30, 41, 59, 0.4));
  color: var(--text);
  box-shadow: 0 8px 24px rgba(79, 70, 229, 0.15), inset 0 0 0 1px rgba(99, 102, 241, 0.2);
}''',
    css, flags=re.DOTALL
)

# 6. Soften metric-tile colors
css = re.sub(
    r'\.metric-tile-emerald strong\s*\{\s*color:\s*#4ade80;\s*\}',
    r'.metric-tile-emerald strong { color: #6ee7b7; text-shadow: 0 0 12px rgba(16, 185, 129, 0.2); }',
    css, flags=re.DOTALL
)
css = re.sub(
    r'\.metric-tile-amber strong\s*\{\s*color:\s*#fbbf24;\s*\}',
    r'.metric-tile-amber strong { color: #fcd34d; text-shadow: 0 0 12px rgba(245, 158, 11, 0.2); }',
    css, flags=re.DOTALL
)
css = re.sub(
    r'\.metric-tile-indigo strong\s*\{\s*color:\s*#a5b4fc;\s*\}',
    r'.metric-tile-indigo strong { color: #c7d2fe; text-shadow: 0 0 12px rgba(99, 102, 241, 0.3); }',
    css, flags=re.DOTALL
)

# 7. memory-signal-card glassmorphism
css = re.sub(
    r'\.memory-signal-card\s*\{[^}]*\}',
    r'''.memory-signal-card {
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(39, 39, 42, 0.3), rgba(24, 24, 27, 0.4));
  border: 1px solid rgba(82, 82, 91, 0.35);
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(8px);
}''',
    css, flags=re.DOTALL
)

# 8. Modernize stats card (the ones in the top grid)
css = re.sub(
    r'\.modern-stat-card\s*\{[^}]*\}',
    r'''.modern-stat-card {
  padding: 16px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(24, 24, 27, 0.6), rgba(14, 14, 18, 0.7));
  backdrop-filter: blur(20px);
  border: 1px solid rgba(82, 82, 91, 0.3);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}''',
    css, flags=re.DOTALL
)


with open(file_path, 'w') as f:
    f.write(css)

