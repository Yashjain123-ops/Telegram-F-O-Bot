import pickle
import os

try:
    with open('project_alpha/data/state.pkl', 'rb') as f:
        state = pickle.load(f)['data']
except Exception as e:
    print(f"Error loading state: {e}")
    state = {}

print("=== SIGNAL STORE ===")
signal_store = state.get('signal_store')
if signal_store:
    signals = getattr(signal_store, 'signals', {})
    if isinstance(signals, dict):
        print(f"Total Signals: {len(signals)}")
        for k, v in signals.items():
            print(f"  {k}: {getattr(v, 'stage', 'UNKNOWN')}")
    else:
        print(f"Signals: {signals}")

print("=== VALIDATION ENGINE ===")
val = state.get('validation_engine')
if val:
    print(f"Rejections: {getattr(val, 'rejections', 0)}")
    
print("=== PAPER TRADING ===")
pt = state.get('paper_trading')
if pt:
    print(f"Portfolio value: {getattr(pt, 'capital', 0)}")
    
print("Let's look at the object attributes if needed.")
