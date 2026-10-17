"""One-off ablation: does injecting the customer profile as a RAGAS context
entry measurably change faithfulness? This is the required Task 2 rubric
item: 'one change to the pipeline with before/after scores and a judgement
on whether it helped.'
"""
import pandas as pd

without = pd.read_csv("docs/lab3-evidence/rag_eval_no_profile.csv")
with_ = pd.read_csv("docs/lab3-evidence/rag_eval_with_profile.csv")

print("=== Profile-context injection ablation ===")
for metric in ("faithfulness", "answer_relevancy", "context_recall"):
    if metric in without.columns and metric in with_.columns:
        before = without[metric].mean()
        after = with_[metric].mean()
        print(f"  {metric:20s} before={before:.3f}  after={after:.3f}  "
              f"delta={after - before:+.3f}")

combined = pd.concat([
    without.assign(profile_context=False),
    with_.assign(profile_context=True),
])
combined.to_csv("docs/lab3-evidence/profile-injection-ablation.csv", index=False)
print("\nWrote docs/lab3-evidence/profile-injection-ablation.csv")
