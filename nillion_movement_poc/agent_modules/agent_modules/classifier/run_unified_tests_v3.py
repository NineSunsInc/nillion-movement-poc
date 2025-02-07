################################################################
# File: run_unified_tests_v3.py
################################################################

import os

from datetime import datetime
from pathlib import Path

# 1) Import the updated safety+domain pipeline
#    (Now from ft_domain_action_classifier_v3.py)
from agent_modules.classifier.domain.ft_domain_action_classifier_v3 import TwoStageClassifierV3, ResultLogger, evaluate_results

# 2) Import your DistilBERT-based BlockchainActionClassifier
from agent_modules.classifier.blockchain_action.ft_blockchain_actions_classifier import BlockchainActionClassifier

# 3) Import the same prompts and logger from your existing code
#    so we can replicate the standard test categories
from agent_modules.classifier.domain.domains_test_prompts import (
    STANDARD_FINANCIAL_QUERIES, 
    STANDARD_INFORMATIONAL_QUERIES,
    STANDARD_PRIVATE_VAULT_QUERIES, 
    SAFE_PROMPTS, 
    UNSAFE_PROMPTS, 
    BENIGN_PROMPTS,
    MALICIOUS_PROMPTS, 
    MIXED_PROMPTS, 
    IN_DOMAIN_AND_VAGUE_QUERIES,
    OUT_OF_DOMAIN_QUERIES, 
    NEED_CLARIFICATION_QUERIES
)

from agent_modules.classifier.eval_unified_tests import ResultsComparator

# 4) Import the blockchain action sub-category test prompts
from agent_modules.classifier.blockchain_action.blockchain_action_subcat_test import (
    BA_TOKEN_PRICE_TEST_PROMPTS, 
    BA_TOKEN_QUERY_TEST_PROMPTS, 
    BA_PAIR_PRICE_TEST_PROMPTS, 
    BA_PAIR_QUERY_TEST_PROMPTS, 
    BA_TRADE_TEST_PROMPTS, 
    BA_SEND_TEST_PROMPTS, 
    BA_CROSS_CHAIN_TEST_PROMPTS,
    BA_OTHER_TEST_PROMPTS
)

# Define model directories as module-level constants
DOMAIN_MODEL_DIR = Path(__file__).resolve().parent / "fine_tuned_domain_distilbert"
BLOCKCHAIN_MODEL_DIR = Path(__file__).resolve().parent / "fine_tuned_blockchain_action"
CLASSIFICATION_RESULTS_DIR = Path(__file__).resolve().parent / "classification_results"

################################################################
# UnifiedMainClassifierV3
################################################################
class UnifiedMainClassifierV3:
    """
    This aggregator uses the TwoStageClassifierV3 for safety+domain,
    then if domain == 'blockchain_action', we pass to BlockchainActionClassifier
    to determine subcategory (trade, send, token_price, etc.).
    """

    def __init__(self, 
            domain_model_dir=DOMAIN_MODEL_DIR,
            blockchain_model_dir=BLOCKCHAIN_MODEL_DIR
        ):
        # 1) Our two-stage pipeline (safety + domain) using DistilBERT domain classifier
        self.domain_pipeline = TwoStageClassifierV3(domain_model_dir)

        # 2) Our DistilBERT sub-classifier for blockchain_action
        self.blockchain_subclassifier = BlockchainActionClassifier(blockchain_model_dir)

    def classify(self, text: str) -> dict:
        domain_result = self.domain_pipeline.classify(text)
        return self.blockchain_subclassifier.classify_with_domain_result(domain_result, text)

################################################################
# Main test harness
################################################################
def main():
    # We instantiate our "unified" aggregator, pointing to 
    # your fine-tuned DistilBERT domain model & blockchain action model
    unified_classifier = UnifiedMainClassifierV3(
        domain_model_dir=DOMAIN_MODEL_DIR,
        blockchain_model_dir=BLOCKCHAIN_MODEL_DIR
    )

    # Create timestamp for the output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = CLASSIFICATION_RESULTS_DIR / f"/subcategorization_tests/ft_unified_with_others_data_v6.1_{timestamp}.json"
    
    # Create a logger with the output file
    logger = ResultLogger(output_file)

    # Same categories of prompts we used before
    categories = [
        ("Safe Prompts", SAFE_PROMPTS),
        ("Benign Prompts", BENIGN_PROMPTS),
        ("Unsafe Prompts", UNSAFE_PROMPTS),
        ("Malicious Prompts", MALICIOUS_PROMPTS),
        ("In-Domain & Vague Prompts", IN_DOMAIN_AND_VAGUE_QUERIES),
        ("Mixed Prompts", MIXED_PROMPTS),
        ("Out-of-Domain", OUT_OF_DOMAIN_QUERIES),
        ("Standard Financial Prompts", STANDARD_FINANCIAL_QUERIES),
        ("Standard Informational Prompts", STANDARD_INFORMATIONAL_QUERIES),
        ("Standard Private Vault Prompts", STANDARD_PRIVATE_VAULT_QUERIES),
        ("Need Clarification", NEED_CLARIFICATION_QUERIES),
        ("Blockchain Action Token Price", BA_TOKEN_PRICE_TEST_PROMPTS),
        ("Blockchain Action Token Query", BA_TOKEN_QUERY_TEST_PROMPTS),
        ("Blockchain Action Pair Price", BA_PAIR_PRICE_TEST_PROMPTS),
        ("Blockchain Action Pair Query", BA_PAIR_QUERY_TEST_PROMPTS),
        ("Blockchain Action Trade", BA_TRADE_TEST_PROMPTS),
        ("Blockchain Action Send", BA_SEND_TEST_PROMPTS),
        ("Blockchain Action Cross Chain", BA_CROSS_CHAIN_TEST_PROMPTS),
        ("Blockchain Action Other", BA_OTHER_TEST_PROMPTS),
    ]

    # Evaluate them all
    for category, prompts in categories:
        results = evaluate_results(unified_classifier, prompts, category)
        # Log results using our standard logger
        for result in results:
            logger.log_result(category, result['prompt'], result)

    # Save the combined JSON output
    logger.save()
    print(f"\nResults saved to: {logger.output_file}")
    
    # Optional: Run comparison if old file is provided
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--compare-with', '-c', 
                       help='Path to previous results file to compare with')
    args = parser.parse_args()
    
    if args.compare_with:
        print(f"\nComparing with previous results: {args.compare_with}")
        evaluator = ResultsComparator(logger.output_file, args.compare_with)
        eval_file = evaluator.save_comparison("classification_results/subcategorization_tests/")
        print(f"Comparison saved to: {eval_file}")
    else:
        print("\nNo comparison file provided. Run with --compare-with to compare with previous results.")
        print("Example:")
        print(f"python run_unified_tests_v3.py --compare-with classification_results/subcategorization_tests/ft_unified_v5_20250112_191026.json")

################################################################
# Entry point
################################################################
if __name__ == "__main__":
    main()