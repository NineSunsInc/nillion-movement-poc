############################################################
# File: ft_domain_action_classifier_v3.py
############################################################
import os
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import torch
from transformers import (
    DistilBertTokenizerFast,
    DistilBertForSequenceClassification,
    pipeline,
    AutoTokenizer,
    AutoModelForSequenceClassification
)

DOMAIN_MODEL_DIR = Path(__file__).resolve().parent.parent / "fine_tuned_domain_distilbert"

############################################################
# 1) Safety Classification DataClass
############################################################
@dataclass
class SafetyClassification:
    status: str
    safety_score: float
    triggered_keywords: List[str]
    reason: Optional[str] = None
    domain_categories: Optional[Dict] = None


############################################################
# 2) Logger
############################################################
class ResultLogger:
    def __init__(self, output_file: str):
        self.output_file = output_file
        self.results = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "model_version": "3",
                "categories_evaluated": []
            },
            "results_by_category": {}
        }

    def log_result(self, category: str, prompt: str, result: dict):
        if category not in self.results["results_by_category"]:
            self.results["results_by_category"][category] = []
            if category not in self.results["metadata"]["categories_evaluated"]:
                self.results["metadata"]["categories_evaluated"].append(category)
        
        self.results["results_by_category"][category].append(result)

    def save(self):
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\nResults saved to: {self.output_file}")

    def _add_summary_statistics(self):
        rejection_reasons = {}
        rejection_keywords = {}

        for category, results in self.results['results_by_category'].items():
            if not results:
                continue

            accepted = sum(1 for r in results if r['status'] == 'accepted')
            rejected = sum(1 for r in results if r['status'] == 'rejected')
            needs_clarification = sum(1 for r in results if r['status'] == 'needs_clarification')
            total = len(results)

            if rejected > 0:
                category_rejections = [r for r in results if r['status'] == 'rejected']
                reasons = {}
                keywords = set()
                for r in category_rejections:
                    reason = r.get('reason', 'unknown')
                    reasons[reason] = reasons.get(reason, 0) + 1
                    for kw in r.get('triggered_keywords', []):
                        keywords.add(kw)
                rejection_reasons[category] = reasons
                rejection_keywords[category] = list(keywords)

            if total > 0:
                self.results['summary_statistics'][category] = {
                    'total': total,
                    'accepted': accepted,
                    'rejected': rejected,
                    'needs_clarification': needs_clarification,
                    'acceptance_rate': f"{(accepted/total)*100:.1f}%",
                    'rejection_rate': f"{(rejected/total)*100:.1f}%",
                    'clarification_rate': f"{(needs_clarification/total)*100:.1f}%"
                }

        self.results['rejection_analysis'] = {
            'reasons_by_category': rejection_reasons,
            'triggered_keywords_by_category': rejection_keywords
        }

    def _check_for_issues(self, prompt, result):
        if result.get('safety_score', 0.0) > 0.4 and result.get('status') == 'accepted':
            self.results['potential_issues'].append(
                f"High safety score prompt accepted: {prompt}"
            )

        domain_categories = result.get('domain_categories', {})
        if domain_categories.get('is_in_domain') is False and result.get('status') == 'accepted':
            self.results['potential_issues'].append(
                f"Out-of-domain prompt accepted: {prompt}"
            )

############################################################
# 3) MetaGuardSafetyClassifier: 
#    we keep or add new malicious phrases for "hide transactions," "scam," etc.
############################################################
class MetaGuardSafetyClassifier:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained("meta-llama/Prompt-Guard-86M")
        self.model = AutoModelForSequenceClassification.from_pretrained("meta-llama/Prompt-Guard-86M")
        self.safety_pipeline = pipeline("text-classification", model=self.model, tokenizer=self.tokenizer)

        # Danger or malicious phrases (we can add "hide transactions," "scam," "phishing," "vulnerabilities," etc.)
        self.danger_phrases = [
            "front-run", "rugpull", "pump scheme", "ponzi", "exploit", "hack", 
            "steal", "drain", "attack", "bypass", "manipulate", "honeypot", 
            "illegal", "backdoor", "malicious", "forge", "spoof", "impersonate",
            "fake", "avoid kyc", "mixer services", "flash loan attack", 
            "hidden backdoor", "exploit contract", "fake bridge", "fake bridge contract",
            "fake bridge smart contract", "reentrancy attack", "hidden admin mint functions",
            "jailbreak", "ignore policy", "bypass system", "disable restrictions",
            "infinite mint", "money laundering", "sybil attack", "harvest private key",
            "extract seed phrase", "steal seed phrase", "steal mnemonic",
            # newly included malicious or suspicious
            "hide transactions", "obscure wallet identity", "avoid detection", 
            "phishing contract", "phishing contract templates", "create scam", "scam presale",
            "scam referral", "scam contract", "find vulnerabilities in this contract", 
        ]
        # user instructing how to do these => immediate reject
        self.malicious_instructions = [
            "how to", "guide me to", "please show me how to", 
            "best ways to", "methods to"
        ]

    def fuzzy_replace(self, text: str) -> str:
        replaced = text
        replaced = replaced.replace("0", "o").replace("1", "i").replace("3", "e")
        replaced = replaced.replace("@", "a").replace("$", "s")
        return replaced

    def fuzzy_contains(self, text_lower: str, phrase: str) -> bool:
        if phrase in text_lower:
            return True
        replaced = self.fuzzy_replace(text_lower)
        fuzz_phrase = self.fuzzy_replace(phrase)
        return (fuzz_phrase in replaced)

    def is_suspected_malicious(self, text_lower: str) -> bool:
        # If any of these dangerous phrases appear
        for dp in self.danger_phrases:
            if dp in text_lower:
                return True
        return False

    def is_safe_prompt(self, text: str) -> Tuple[bool, float, List[str]]:
        text_lower = text.lower()
        triggers: List[str] = []

        # Step A: if user says "how to hide transactions" or "best ways to create scam," => reject
        for dp in self.danger_phrases:
            if dp in text_lower:
                # if user is instructing => reject
                # or if it's obviously malicious => reject
                # We do not do "avoid vs. do malicious" here for simplicity
                triggers.append(dp)
                return (False, 1.0, triggers)

        # Step B: meta-llama pipeline
        out = self.safety_pipeline(text, truncation=True)[0]
        label = out["label"].upper()
        score = float(out["score"])

        if label == "UNSAFE":
            triggers.append("meta_llama_guard")
            return (False, 1.0, triggers)

        safety_score = (1.0 - score)*0.2
        return (True, safety_score, triggers)

############################################################
# 4) DistilBertDomainClassifier: 
#    we add a generic "info_keywords" and "web3_keywords" approach
############################################################
class DistilBertDomainClassifier:
    def __init__(self, model_dir: str):
        self.tokenizer = DistilBertTokenizerFast.from_pretrained(model_dir)
        self.model = DistilBertForSequenceClassification.from_pretrained(model_dir)

        config_path = os.path.join(model_dir, "domain_label_config.json")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"domain_label_config.json not found at: {model_dir}")
        with open(config_path, "r") as f:
            data = json.load(f)
            self.label2id = data["label2id"]
            self.id2label = {int(k): v for k, v in data["id2label"].items()}

        self.model.eval()
        self.model.to("cpu")

        # subdomains
        self.web3_subdomains = {
            "mighty": [
                "mighty network", "mighty sdk", "mighty league", "mighty notifications", "agentic", "mighty "
            ],
            "partners": [
                "polygon", "movement labs", "0g labs", "nillion", "bitcoinos", "pol ", " btc", "move token", "polygon network", "arb", "arbitrum", "arbitrum network"
            ]
        }
        # typical triggers for blockchain_action
        self.blockchain_triggers = [
            "send", "transfer", "swap", "trade", "bridge",
            "price", "cost", "going rate", "market cap", "fully diluted",
            "minted supply", "apy", "impermanent loss", "volume", "liquidity pool"
        ]
        self.wallet_balance_triggers = [
            "my wallet balance", "my balance", "my holdings", "my eth holdings", "my token holdings", "my current wallet balance", "my complete wallet balance"
        ]
        self.private_data_terms = [
            "my address", "my phone", "my email", "my date of birth", "my dob"
        ]

        # For a general "info" approach, we create two sets of heuristics:
        self.info_keywords = [
            "how does", "what is", "how to", "explain", "tell me more", "teach me",
            "information on", "inquiry", "guide", "practices", "tips", "best practice",
            "checklist", "compliance", "risk", "monitoring", "privacy", "regulatory", "safe",
            "security", "audit", "transaction", "withdrawal", "requirements"
        ]

        self.web3_keywords = [
            "crypto", "blockchain", "web3", "lending", "trading", "bitcoin", "eth", "ethereum", "stablecoin", "ethereum", "evm", "move", "solidity", "yields", 'secure wallet', 'data vaults', "smart contract", "defi", "dex",
            "token", "staking", "yield farming", "smart contract", "lend", "borrowing", "dex", 
            "platforms", "practices", "management", "monitoring", "limits", "safety", "compliance"
        ]

    def classify_domain(self, text: str) -> Tuple[str, float]:
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, padding=True)
        with torch.no_grad():
            output = self.model(**inputs)
            logits = output.logits
            pred_id = logits.argmax(dim=-1).item()
            probs = torch.nn.functional.softmax(logits, dim=-1)[0]
            conf = float(probs[pred_id])
        label_name = self.id2label[pred_id]
        return label_name, conf

    def classify_subdomain_web3(self, text_lower: str) -> str:
        for subcat, keys in self.web3_subdomains.items():
            for kw in keys:
                if kw in text_lower:
                    return subcat
        return "general"

    def override_wallet_balance(self, text_lower: str, label: str, conf: float) -> Tuple[str, float]:
        for phrase in self.wallet_balance_triggers:
            if phrase in text_lower:
                # if not out_of_domain => set blockchain_action
                if label not in ["blockchain_action", "out_of_domain"]:
                    label = "blockchain_action"
                    conf = max(conf, 0.95)
                break
        return label, conf

    def override_blockchain_action(self, text_lower: str, label: str, conf: float) -> Tuple[str, float]:
        for kw in self.blockchain_triggers:
            if kw in text_lower:
                if label not in ["out_of_domain"]:
                    label = "blockchain_action"
                    conf = max(conf, 0.95)
                break
        return label, conf

    def override_private_data(self, text_lower: str, label: str, conf: float) -> Tuple[str, float]:
        for term in self.private_data_terms:
            if term in text_lower:
                label = "private_data"
                conf = max(conf, 0.9)
                break
        return label, conf

    def check_info_web3(self, text_lower: str) -> bool:
        """
        If user text includes at least ONE 'info keyword' AND one 'web3 keyword',
        we consider it web3_information by default.
        E.g. "safe lending platforms" => "safe" is an info keyword, 
        "lending" is a web3 keyword => override to web3_information.
        """
        # check if it has an info keyword
        has_info = any(ik in text_lower for ik in self.info_keywords)
        # check if it has a web3 keyword
        has_web3 = any(wk in text_lower for wk in self.web3_keywords)
        return (has_info and has_web3)

    def classify(self, text: str) -> Dict:
        text_lower = text.lower().strip()
        
        # **Early override for prompts that ask about capabilities**
        capability_phrases = ["what can you do", "tell me what you can do", "what do you do", "tell me more about your capabilities", "what can mighty service do?", "what can this demo do?"]
        for phrase in capability_phrases:
            if phrase in text_lower:
                return {
                    'status': 'accepted',
                    'safety_score': 0.0,
                    'triggered_keywords': [],
                    'domain_categories': {
                        'is_in_domain': True,
                        'category_scores': [{
                            'category': "web3_information",
                            'confidence': 0.95
                        }],
                        'subdomain': "general"
                    }
                }
        
        # 0) short => needs clarification
        if len(text_lower.split()) < 2:
            return {
                'status': 'needs_clarification',
                'safety_score': 0.0,
                'triggered_keywords': [],
                'reason': 'insufficient_input',
                'ambiguity_type': 'short_prompt',
                'clarification_needed': True
            }
        
        # 1) DistilBERT classification (rest of your existing logic)
        raw_label, raw_conf = self.classify_domain(text_lower)
        
        # 2) If the prompt includes an info keyword + web3 keyword => forcibly label = web3_information
        if self.check_info_web3(text_lower):
            label = "web3_information"
            conf = 0.95
        else:
            label, conf = raw_label, raw_conf
        
        # 3) Override wallet_balance, blockchain_action, private_data etc.
        label, conf = self.override_wallet_balance(text_lower, label, conf)
        label, conf = self.override_blockchain_action(text_lower, label, conf)
        label, conf = self.override_private_data(text_lower, label, conf)
        
        if label == "out_of_domain" and conf > 0.65:
            return {
                'status': 'rejected',
                'reason': 'out_of_domain',
                'safety_score': 0.0,
                'triggered_keywords': []
            }
        
        # Final accepted cases
        if label == "web3_information":
            subcat = self.classify_subdomain_web3(text_lower)
            return {
                'status': 'accepted',
                'safety_score': 0.0,
                'triggered_keywords': [],
                'domain_categories': {
                    'is_in_domain': True,
                    'category_scores': [{
                        'category': label,
                        'confidence': conf
                    }],
                    'subdomain': subcat
                }
            }
        elif label == "blockchain_action":
            return {
                'status': 'accepted',
                'safety_score': 0.0,
                'triggered_keywords': [],
                'domain_categories': {
                    'is_in_domain': True,
                    'category_scores': [{
                        'category': label,
                        'confidence': conf
                    }]
                }
            }
        elif label == "private_data":
            return {
                'status': 'accepted',
                'safety_score': 0.0,
                'triggered_keywords': [],
                'domain_categories': {
                    'is_in_domain': True,
                    'category_scores': [{
                        'category': label,
                        'confidence': conf
                    }]
                }
            }
        
        # Fallback to web3_information
        return {
            'status': 'accepted',
            'safety_score': 0.0,
            'triggered_keywords': [],
            'domain_categories': {
                'is_in_domain': True,
                'category_scores': [{
                    'category': "web3_information",
                    'confidence': 0.70
                }],
                'subdomain': "general"
            }
        }


############################################################
# 5) TwoStageClassifierV3
############################################################
class SafetyClassifierV3:
    def __init__(self):
        self.safety_guard = MetaGuardSafetyClassifier()

    def classify(self, text: str) -> Dict:
        is_safe, safety_score, triggers = self.safety_guard.is_safe_prompt(text)

        if not is_safe:
            return {
                'status': 'rejected',
                'reason': 'unsafe_content',
                'safety_score': safety_score,
                'triggered_keywords': triggers
            }

        return {
            'status': 'accepted',
            'safety_score': safety_score,
            'triggered_keywords': triggers
        }
    
class DomainClassifierV3:
    def __init__(self, domain_model_dir=DOMAIN_MODEL_DIR):
        self.domain_classifier = DistilBertDomainClassifier(domain_model_dir)

    def classify(self, text: str, safety_score: float, triggers: List[str]) -> Dict:
        domain_result = self.domain_classifier.classify(text)
        domain_result['safety_score'] = max(domain_result.get('safety_score', 0.0), safety_score)

        # merge triggers
        if 'triggered_keywords' in domain_result:
            domain_result['triggered_keywords'].extend(triggers)
        else:
            domain_result['triggered_keywords'] = triggers

        return domain_result

class TwoStageClassifierV3:
    """
    Stage A: MetaGuardSafetyClassifier (reject malicious or suspicious)
    Stage B: DistilBertDomainClassifier (with check_info_web3 logic).
    """
    def __init__(self, domain_model_dir=DOMAIN_MODEL_DIR):
        self.safety_guard = SafetyClassifierV3()
        self.domain_classifier = DomainClassifierV3(domain_model_dir)

    def classify(self, text: str) -> Dict:
        # A) Safety
        safety_result = self.safety_guard.classify(text)
        if safety_result['status'] == 'rejected':
            return safety_result

        # B) Domain
        domain_result = self.domain_classifier.classify(text, safety_result['safety_score'], safety_result['triggered_keywords'])
        return domain_result


############################################################
# Evaluate function
############################################################
def evaluate_results(classifier, prompts, category_name):
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
                for sc in domain_results.get('category_scores', []):
                    print(f"  • {sc['category']}: {sc['confidence']:.3f}")
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