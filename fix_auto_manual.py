import re

file_path = '/home/acer/Downloads/AuraCore/frontend/app/globals.css'
with open(file_path, 'r') as f:
    css = f.read()

# 1. Update .activity-meta-row
css = re.sub(
    r'\.activity-meta-row\s*\{[^}]*\}',
    r'''.activity-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: linear-gradient(90deg, rgba(39, 39, 42, 0.4), rgba(24, 24, 27, 0.5));
  backdrop-filter: blur(8px);
  border: 1px solid rgba(82, 82, 91, 0.35);
  color: rgba(228, 228, 231, 0.88);
  font-size: 0.85rem;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
}''',
    css, flags=re.DOTALL
)

# 2. Update .automation-setting-card
css = re.sub(
    r'\.automation-setting-card\s*\{[^}]*\}',
    r'''.automation-setting-card {
  display: grid;
  gap: 16px;
  padding: 20px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(79, 70, 229, 0.12), transparent 40%),
    linear-gradient(180deg, rgba(24, 24, 27, 0.65), rgba(12, 12, 16, 0.75));
  backdrop-filter: blur(20px);
  border: 1px solid rgba(82, 82, 91, 0.35);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}''',
    css, flags=re.DOTALL
)

# 3. Update automation checkbox
css = re.sub(
    r'\.automation-toggle-row input\[type="checkbox"\]\s*\{[^}]*\}',
    r'''.automation-toggle-row input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: #6366f1;
  cursor: pointer;
  transition: transform 150ms ease;
}
.automation-toggle-row input[type="checkbox"]:hover {
  transform: scale(1.1);
}''',
    css, flags=re.DOTALL
)

# 4. Update automation number field
css = re.sub(
    r'\.automation-number-field input\s*\{[^}]*\}',
    r'''.automation-number-field input {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(82, 82, 91, 0.42);
  background: rgba(9, 9, 11, 0.6);
  color: #f4f4f5;
  padding: 12px 14px;
  font: inherit;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: all 200ms ease;
}''',
    css, flags=re.DOTALL
)

css = re.sub(
    r'\.automation-number-field input:focus\s*\{[^}]*\}',
    r'''.automation-number-field input:focus {
  outline: none;
  border-color: rgba(99, 102, 241, 0.6);
  background: rgba(18, 18, 22, 0.8);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2), inset 0 2px 4px rgba(0, 0, 0, 0.1);
}''',
    css, flags=re.DOTALL
)

# 5. Update .manual-info-card
css = re.sub(
    r'\.manual-info-card\s*\{[^}]*\}',
    r'''.manual-info-card {
  display: grid;
  gap: 10px;
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(24, 24, 27, 0.6), rgba(12, 12, 16, 0.7));
  backdrop-filter: blur(12px);
  border: 1px solid rgba(82, 82, 91, 0.3);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.04);
  transition: transform 200ms ease, border-color 200ms ease;
}
.manual-info-card:hover {
  transform: translateY(-2px);
  border-color: rgba(99, 102, 241, 0.4);
}''',
    css, flags=re.DOTALL
)

# 6. Update .manual-step and the circle
css = re.sub(
    r'\.manual-step\s*\{[^}]*\}',
    r'''.manual-step {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 16px;
  align-items: start;
  padding: 16px 18px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(24, 24, 27, 0.5), rgba(12, 12, 16, 0.6));
  backdrop-filter: blur(12px);
  border: 1px solid rgba(82, 82, 91, 0.3);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}''',
    css, flags=re.DOTALL
)

css = re.sub(
    r'\.manual-step > span\s*\{[^}]*\}',
    r'''.manual-step > span {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(99, 102, 241, 0.18);
  border: 1px solid rgba(99, 102, 241, 0.4);
  color: #c7d2fe;
  font-weight: 700;
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.2);
}''',
    css, flags=re.DOTALL
)

with open(file_path, 'w') as f:
    f.write(css)

