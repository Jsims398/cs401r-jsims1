"""Track B evaluation driver. Runs the RAGAS harness against the pipeline
N times (handout: "run the evaluation two or three times and report the
mean and range" -- identical runs moved faithfulness by about +-0.1 on
the reference pipeline), and writes the combined evidence CSV.

Builds its own Bedrock judge instead of evaluation_harness.build_bedrock_judge():
that function's ChatBedrock has no max_tokens set, and the faithfulness metric's
multi-statement decomposition is long enough to hit the default ceiling and come
back as LLMDidNotFinishException -- verified live, 11 of 12 faithfulness calls
failed that way with the harness's default judge. This driver is our own code,
not the shared harness file, so the fix lives here rather than in
evaluation_harness.py.

Usage: python evaluation/run_track_b.py --runs 3
"""

import argparse
import os
from functools import partial

import pandas as pd
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_recall, faithfulness

from evaluation.evaluation_harness import OFFER_TEST_CASES, DEFAULT_BEDROCK_MODEL_ID
from rag.pipeline import invoke as pipeline_invoke

OUTPUT_PATH = "docs/lab3-evidence/rag_eval.csv"
JUDGE_MAX_TOKENS = 4096


def build_judge(model_id: str = DEFAULT_BEDROCK_MODEL_ID, region: str = "us-east-1"):
    """Same judge model and embedding model as evaluation_harness.build_bedrock_judge,
    but with max_tokens raised so faithfulness's longer reasoning chain can finish."""
    from langchain_aws import ChatBedrock, BedrockEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    llm = LangchainLLMWrapper(ChatBedrock(
        model_id=model_id, region_name=region,
        max_tokens=JUDGE_MAX_TOKENS,
        model_kwargs={"temperature": 0},
    ))
    embeddings = LangchainEmbeddingsWrapper(BedrockEmbeddings(
        model_id="amazon.titan-embed-text-v2:0", region_name=region,
    ))
    return llm, embeddings


def run_ragas_once(invoke_fn, test_cases, llm, embeddings) -> pd.DataFrame:
    """Mirrors evaluation_harness.RAGEvaluator.run()'s dataset construction,
    against our own higher-max-tokens judge."""
    dataset_dict = {"question": [], "answer": [], "contexts": [], "ground_truth": []}
    for tc in test_cases:
        result = invoke_fn(tc.customer_context, tc.question)
        dataset_dict["question"].append(tc.question)
        dataset_dict["answer"].append(result["answer"])
        dataset_dict["contexts"].append(result["contexts"])
        dataset_dict["ground_truth"].append(tc.ground_truth)

    dataset = Dataset.from_dict(dataset_dict)
    scores = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_recall],
        llm=llm,
        embeddings=embeddings,
    )
    df = scores.to_pandas()
    df["customer_id"] = [tc.customer_id for tc in test_cases]
    return df


def main():
    parser = argparse.ArgumentParser(description="Run Track B RAGAS evaluation")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--query-strategy", type=str, default="hybrid")
    parser.add_argument("--include-profile-context", action="store_true", default=True)
    parser.add_argument("--no-profile-context", dest="include_profile_context",
                        action="store_false")
    parser.add_argument("--output", type=str, default=OUTPUT_PATH,
                        help="CSV path to write (default: docs/lab3-evidence/rag_eval.csv) "
                             "-- override for one-off runs (e.g. an ablation) so they don't "
                             "clobber the graded multi-run evidence file")
    args = parser.parse_args()

    invoke_fn = partial(
        pipeline_invoke,
        query_strategy=args.query_strategy,
        include_profile_context=args.include_profile_context,
    )

    llm, embeddings = build_judge()

    all_runs = []
    for run_idx in range(args.runs):
        print(f"\n{'='*60}\nRun {run_idx + 1}/{args.runs}\n{'='*60}")
        df = run_ragas_once(invoke_fn, OFFER_TEST_CASES, llm, embeddings)
        df["run"] = run_idx + 1
        all_runs.append(df)
        for metric in ("faithfulness", "answer_relevancy", "context_recall"):
            if metric in df.columns:
                print(f"  {metric:20s} values: {list(df[metric].round(3))}")

    combined = pd.concat(all_runs, ignore_index=True)

    os.makedirs("docs/lab3-evidence", exist_ok=True)
    combined.to_csv(args.output, index=False)
    print(f"\nWrote {len(combined)} rows ({args.runs} runs x {len(OFFER_TEST_CASES)} cases) "
          f"to {args.output}")
    print(f"Judge model: {DEFAULT_BEDROCK_MODEL_ID} (max_tokens={JUDGE_MAX_TOKENS})")

    print("\n=== Per-metric mean and range across all runs ===")
    for metric in ("faithfulness", "answer_relevancy", "context_recall"):
        if metric in combined.columns:
            values = combined[metric].dropna()
            print(f"  {metric:20s} mean={values.mean():.3f}  "
                  f"range=[{values.min():.3f}, {values.max():.3f}]  "
                  f"n={len(values)} (of {len(combined)}, NaN = failed judge call)")


if __name__ == "__main__":
    main()
