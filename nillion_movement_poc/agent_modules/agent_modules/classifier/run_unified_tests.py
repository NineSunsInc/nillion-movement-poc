import os
from datetime import datetime
import json
from pathlib import Path

# 1) Import the existing safety + domain pipeline
#    (This is the TwoStageClassifier from your code snippet)
from agent_modules.classifier.domain.ft_domain_action_classifier_v2 import TwoStageClassifier, ResultLogger

# 2) Import your new DistilBERT-based BlockchainActionClassifier
from agent_modules.classifier.blockchain_action.ft_blockchain_actions_classifier import BlockchainActionClassifier

# 3) Import the same prompts and logger from your existing code
#    so we can replicate the standard test categories
from agent_modules.classifier.domain.domains_test_prompts import (
    STANDARD_FINANCIAL_QUERIES, STANDARD_INFORMATIONAL_QUERIES,
    STANDARD_PRIVATE_VAULT_QUERIES, SAFE_PROMPTS, UNSAFE_PROMPTS, BENIGN_PROMPTS,
    MALICIOUS_PROMPTS, MIXED_PROMPTS, IN_DOMAIN_AND_VAGUE_QUERIES,
    OUT_OF_DOMAIN_QUERIES, NEED_CLARIFICATION_QUERIES
)

from agent_modules.classifier.blockchain_action.blockchain_action_subcat_test import BA_TOKEN_PRICE_TEST_PROMPTS, BA_TOKEN_QUERY_TEST_PROMPTS, BA_PAIR_PRICE_TEST_PROMPTS, BA_PAIR_QUERY_TEST_PROMPTS, BA_TRADE_TEST_PROMPTS, BA_SEND_TEST_PROMPTS, BA_CROSS_CHAIN_TEST_PROMPTS

BLOCKCHAIN_MODEL_DIR = Path(__file__).resolve().parent / "fine_tuned_blockchain_action"

def evaluate_results(classifier, prompts, category_name):
    """
    Evaluates a batch of prompts using the given classifier, prints results,
    and returns them so we can log with ResultLogger.
    """
    results = []
    print(f"\nEvaluating {category_name}:")
    print("=" * 80)
    rejected_count = 0
    needs_clarification_count = 0
    rejection_reasons = {}

    for prompt in prompts:
        result = classifier.classify(prompt)
        results.append({'category': category_name, 'prompt': prompt, **result})

        print(f"\nPrompt: {prompt}")
        print(f"Status: {result['status']}")

        if result['status'] == 'rejected':
            rejected_count += 1
            reason = result.get('reason', 'unknown')
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            print(f"❌ REJECTED - Reason: {reason}")
            print(f"Safety Score: {result.get('safety_score', 0.0):.3f}")
            if 'triggered_keywords' in result:
                for keyword in result['triggered_keywords']:
                    print(f"  • {keyword}")

        elif result['status'] == 'needs_clarification':
            needs_clarification_count += 1
            print("⚠️ Needs clarification!")
            if 'reason' in result:
                print(f"Reason: {result['reason']}")

        elif result['status'] == 'accepted':
            domain_results = result.get('domain_categories', {})
            if domain_results:
                print("\nDomain Categories:")
                for score in domain_results.get('category_scores', []):
                    print(f"  • {score['category']}: {score['confidence']:.3f}")
                print(f"Is In-Domain: {domain_results.get('is_in_domain', False)}")

                subdomain = domain_results.get('subdomain')
                if subdomain:
                    print(f"Subdomain: {subdomain}")

    print(f"\n{category_name} Summary:")
    print(f"Total Prompts: {len(prompts)}")
    print(f"Rejected: {rejected_count} ({(rejected_count/len(prompts))*100:.1f}%)")
    print(f"Needs Clarification: {needs_clarification_count} ({(needs_clarification_count/len(prompts))*100:.1f}%)")
    if rejection_reasons:
        print("\nRejection Reasons:")
        for reason, count in rejection_reasons.items():
            print(f"  • {reason}: {count}")

    return results


class UnifiedMainClassifier:
    """
    This aggregator uses the TwoStageClassifier for safety+domain,
    then if domain == 'blockchain_action', we pass to BlockchainActionClassifier
    to determine subcategory (trade, send, token_price, etc.).
    """

    def __init__(self, blockchain_model_dir=BLOCKCHAIN_MODEL_DIR):
        # 1) Our two-stage pipeline (safety + domain)
        self.domain_pipeline = TwoStageClassifier()

        # 2) Our DistilBERT sub-classifier for blockchain_action
        self.blockchain_subclassifier = BlockchainActionClassifier(blockchain_model_dir)

    def classify(self, text: str) -> dict:
        # Step A: Safety + domain
        domain_result = self.domain_pipeline.classify(text)

        if domain_result.get("status") == "accepted":
            dom_cats = domain_result.get("domain_categories", {})
            if dom_cats.get("is_in_domain", False):
                # Suppose the top category is in "category_scores"
                scores = dom_cats.get("category_scores", [])
                if scores:
                    top_category = scores[0]["category"]
                    if top_category == "blockchain_action":
                        # Step B: If domain == blockchain_action,
                        # we call the sub-classifier
                        subcat = self.blockchain_subclassifier.classify(text)
                        # Add subdomain info
                        domain_result["domain_categories"]["subdomain"] = subcat

        return domain_result


def main():
    # We instantiate our "unified" aggregator
    unified_classifier = UnifiedMainClassifier()

    # Create a logger to store results in JSON
    logger = ResultLogger()

    # Same categories of prompts we used before
    categories = [
        ("Safe Prompts", SAFE_PROMPTS),
        ("Benign Prompts", BENIGN_PROMPTS),
        ("Unsafe Prompts", UNSAFE_PROMPTS),
        ("Malicious Prompts", MALICIOUS_PROMPTS),
        ('In-Domain', IN_DOMAIN_AND_VAGUE_QUERIES),
        ('Mixed Prompts', MIXED_PROMPTS),
        ('Out-of-Domain', OUT_OF_DOMAIN_QUERIES),
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
    ]

    # Evaluate them all
    for category, prompts in categories:
        results = evaluate_results(unified_classifier, prompts, category)
        # Log results using our standard logger
        for result in results:
            logger.log_result(category, result['prompt'], result)

    # Save the combined JSON output
    logger.save()


if __name__ == "__main__":
    main()