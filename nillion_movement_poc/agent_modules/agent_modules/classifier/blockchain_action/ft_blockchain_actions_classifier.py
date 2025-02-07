"""
blockchain_action_classifier.py

Example usage:
    python blockchain_action_classifier.py --model_dir ./distilbert_blockchain_action \
       --prompt "Swap 1000 USDT to ETH on Movement Labs"

It will output the predicted category: 'trade', 'token_price', etc.
"""
from pathlib import Path

import argparse
import json
import torch
import os

from typing import Dict
from transformers import AutoTokenizer, DistilBertForSequenceClassification, AutoModelForSequenceClassification

BLOCKCHAIN_MODEL_DIR = Path(__file__).resolve().parent.parent / "fine_tuned_blockchain_action"

class BlockchainActionClassifier:
    def __init__(self, model_dir=BLOCKCHAIN_MODEL_DIR):
        # Use the base DistilBERT tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
        
        # Load the fine-tuned model configuration and weights
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        
        # Load label mapping from config.json
        config_path = os.path.join(model_dir, "config.json")
        with open(config_path, "r") as f:
            config = json.load(f)
            self.label2id = config["label2id"]
            self.id2label = config["id2label"]

        # The recognized categories from your fine-tune, plus "other"
        self.known_categories = {
            "token_price",
            "token_query",
            "pair_price",
            "pair_query",
            "trade",
            "send",
            "cross_chain",
            "wallet_balance",
            "other"
        }

        # Additional “action” keywords that clearly map to "other"
        # because they indicate tasks like taxes, verification, bridging credentials, etc.
        # Note: these are simple heuristics to catch key phrases:
        self.taxes_phrases = [
            "tax", "taxes", "taxable", "tax burden", "tax obligation", "tax calculation",
            "calculate my taxes", "owe in taxes", "tax schedule", "tax loss"
        ]
        self.kyc_phrases = [
            "kyc", "kyb", "re-verification", "verify my identity",
            "passport image", "social security info", "business registration docs"
        ]
        self.proof_phrases = [
            "proof-of-human", "liveness video", "face-liveness", "zero-knowledge kyc",
            "complete a voice id check", "iris-scan", "uniqueness check", "sybil"
        ]
        self.credential_phrases = [
            "link my amazon prime", "netflix subscription proof", "sync my github commits",
            "attach my frequent flyer membership", "spotify premium", "reclaim protocol",
            "microsoft mvp certificate", "linkedin job title", "yelp elite status",
            "college alumni credentials", "gym chain membership", "slack workspace membership"
        ]
        self.complaint_phrases = [
            "file an official complaint", "register a formal dispute", "log a specialized complaint",
            "upload my company's corporate docs", "compliance doc", "aml check", "business-tier compliance",
            "cross-chain compliance token", "accreditation investor status"
        ]

    def classify_with_domain_result(self, domain_result: Dict, text: str) -> str:
        if domain_result.get("status") == "accepted":
            dom_cats = domain_result.get("domain_categories", {})
            if dom_cats.get("is_in_domain", False):
                scores = dom_cats.get("category_scores", [])
                if scores:
                    top_category = scores[0]["category"]
                    if top_category == "blockchain_action":
                        # sub-classify
                        subcat = self.classify(text)
                        domain_result["domain_categories"]["subdomain"] = subcat

        return domain_result

    def classify(self, text: str) -> str:
        # 1) Base DistilBERT classification
        inputs = self.tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            predicted_class_id = logits.argmax(dim=-1).item()

        raw_pred = self.id2label[str(predicted_class_id)]
        text_lower = text.lower()

        # 2) Post-processing: token_query <-> token_price
        if raw_pred == "token_query":
            if any(word in text_lower for word in ["price", "cost", "going rate"]):
                return "token_price"
        elif raw_pred == "token_price":
            # Check if user is actually asking about supply, holders, inflation => token_query
            if any(word in text_lower for word in ["market cap", "governance", "inflation", "supply", "holders"]):
                return "token_query"

        # 3) “Other” override heuristics: if we see key phrases about
        #    taxes, verification, KYC, bridging credentials, or formal complaint, override to "other"
        if (any(tp in text_lower for tp in self.taxes_phrases)
            or any(kp in text_lower for kp in self.kyc_phrases)
            or any(pp in text_lower for pp in self.proof_phrases)
            or any(cp in text_lower for cp in self.credential_phrases)
            or any(sp in text_lower for sp in self.complaint_phrases)):
            return "other"

        # 4) If raw_pred not recognized => fallback to "other"
        if raw_pred not in self.known_categories:
            return "other"

        return raw_pred


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inference script for DistilBERT-based blockchain action classification."
    )
    parser.add_argument("--model_dir",
                        type=str,
                        required=True,
                        help="Path to the fine-tuned DistilBERT model directory.")
    parser.add_argument("--prompt",
                        type=str,
                        required=True,
                        help="User prompt to classify.")
    return parser.parse_args()


def main():
    args = parse_args()
    classifier = BlockchainActionClassifier(args.model_dir)
    predicted_label = classifier.classify(args.prompt)
    print(f"Prompt: {args.prompt}\nPredicted category: {predicted_label}")


if __name__ == "__main__":
    main()