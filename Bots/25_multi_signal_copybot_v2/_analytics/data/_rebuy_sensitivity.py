"""Sensitivity: how does the final BR delta change if we vary the
unresolved-leg recovery factor? This isolates whether the uplift is
real (from resolved rebuys) vs parked capital in unfinished markets."""
import sys, io, os, json, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Import the backtest module functions
spec = importlib.util.spec_from_file_location(
    "_rebuy_trigger_backtest",
    r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\_rebuy_trigger_backtest.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BASE = mod.BASE
with open(mod.ACT, 'r', encoding='utf-8') as f:
    activity = json.load(f)
res_map = mod.build_resolution_map()

# Monkey-patch: we re-run but patch the 0.95 unresolved recovery. Easiest is
# to duplicate the run_backtest function and expose the knob. We just do
# our own math on the results: the unresolved PnL is known per summary.
results = {}
for label, enable in [('control_OFF', False), ('treatment_ON', True)]:
    r = mod.run_backtest(activity, res_map, enable_rebuy=enable)
    results[label] = r['summary']

# Extract all our_cost legs that were unresolved
# This info isn't in summary, we approximate from rebuy data only
# Instead, let's re-run with different recovery. Patch the constant inline.

def rerun_with_recovery(recovery):
    # We modify the module's run_backtest to override 0.95 temporarily
    import types
    # Patch by text-replacement is ugly; simpler: duplicate logic.
    # Instead we just compute incremental sensitivity via the printed summary
    return None

# Manual sensitivity: differentiate outputs
print("Recovery sensitivity (control/treatment final BR as function of unresolved recovery)")
print("=" * 85)
print(f"{'recov':>7} {'control_BR':>12} {'treat_BR':>12} {'delta':>10} {'ctrl_ret':>9} {'treat_ret':>10}")

# Re-run with patched recovery. We need to edit the source temporarily.
import re
src = open(r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\_rebuy_trigger_backtest.py", 'r', encoding='utf-8').read()

for recov in [1.00, 0.95, 0.80, 0.50, 0.0]:
    # replace the specific 0.95 constant (only appears once in settle step)
    patched = src.replace("payout = invested * 0.95", f"payout = invested * {recov:.2f}")
    ns = {}
    exec(compile(patched, '<patched>', 'exec'), ns)
    c = ns['run_backtest'](activity, res_map, enable_rebuy=False)['summary']
    t = ns['run_backtest'](activity, res_map, enable_rebuy=True)['summary']
    print(f"{recov:>7.2f} ${c['final_bankroll']:>11.2f} ${t['final_bankroll']:>11.2f} "
          f"${t['final_bankroll']-c['final_bankroll']:>+9.2f} "
          f"{c['return_pct']*100:>+8.1f}% {t['return_pct']*100:>+9.1f}%")
