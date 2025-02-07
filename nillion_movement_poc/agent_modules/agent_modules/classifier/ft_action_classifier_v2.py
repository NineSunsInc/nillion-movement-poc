import os
from datetime import datetime
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

# Assuming you have these prompt sets somewhere
from agent_modules.classifier.prompts import (
    STANDARD_FINANCIAL_QUERIES, STANDARD_INFORMATIONAL_QUERIES,
    STANDARD_PRIVATE_VAULT_QUERIES, SAFE_PROMPTS, UNSAFE_PROMPTS, BENIGN_PROMPTS,
    IN_DOMAIN_AND_VAGUE_QUERIES, OUT_OF_DOMAIN_QUERIES, MIXED_PROMPTS,
    MALICIOUS_PROMPTS, NEED_CLARIFICATION_QUERIES
)

@dataclass
class SafetyClassification:
    status: str
    safety_score: float
    triggered_keywords: List[str]
    reason: Optional[str] = None
    domain_categories: Optional[Dict] = None

class ResultLogger:
    def __init__(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        current_dir = os.path.dirname(os.path.abspath(__file__))

        self.filename = os.path.join(
            current_dir,
            '..', '..',
            'classification_results',
            'subcategorization_tests',
            f'ft_unified_classifiers_v2_{timestamp}.json'
        )

        self.results = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'model_version': '3.6',  # updated version
                'categories_evaluated': [
                    "Safe Prompts",
                    "Benign Prompts",
                    "Unsafe Prompts",
                    "Malicious Prompts",
                    "In-Domain",
                    "Mixed Prompts",
                    "Out-of-Domain",
                    "Standard Financial Prompts",
                    "Standard Informational Prompts",
                    "Standard Private Vault Prompts",
                    "Need Clarification"
                ]
            },
            'results_by_category': {},
            'rejected_prompts': [],
            'potential_issues': [],
            'summary_statistics': {},
            'rejection_analysis': {}
        }

    def save(self):
        try:
            self._add_summary_statistics()
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"\nResults saved to: {self.filename}")

            if self.results['potential_issues']:
                print("\nPotential Issues Found:")
                for issue in self.results['potential_issues']:
                    print(f"- {issue}")
        except Exception as e:
            print(f"Error saving results: {str(e)}")

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

    def log_result(self, category, prompt, result):
        if category not in self.results['results_by_category']:
            self.results['results_by_category'][category] = []

        result_entry = {
            'prompt': prompt,
            'status': result.get('status', 'unknown'),
            'safety_score': result.get('safety_score', 0.0),
            'triggered_keywords': result.get('triggered_keywords', [])
        }

        if 'reason' in result:
            result_entry['reason'] = result['reason']

        if 'domain_categories' in result:
            result_entry['domain_categories'] = result['domain_categories']

        if result.get('status') == 'rejected':
            result_entry.update({
                'rejection_details': {
                    'safety_score': result.get('safety_score', 0.0),
                    'triggered_keywords': result.get('triggered_keywords', []),
                    'timestamp': datetime.now().isoformat()
                }
            })
            self.results['rejected_prompts'].append(result_entry)

        if result.get('status') == 'needs_clarification':
            result_entry['ambiguity_type'] = result.get('ambiguity_type')
            result_entry['clarification_needed'] = result.get('clarification_needed')

        self.results['results_by_category'][category].append(result_entry)
        self._check_for_issues(prompt, result)

    def _check_for_issues(self, prompt, result):
        if result.get('safety_score', 0.0) > 0.4 and result.get('status') == 'accepted':
            self.results['potential_issues'].append(f"High safety score prompt accepted: {prompt}")

        domain_categories = result.get('domain_categories', {})
        if domain_categories.get('is_in_domain') is False and result.get('status') == 'accepted':
            self.results['potential_issues'].append(
                f"Out-of-domain prompt accepted: {prompt}"
            )


###############################################################################
# 1) Primary Safety Guard with meta-llama and robust heuristics
###############################################################################
class MetaGuardSafetyClassifier:
    """
    Stage 1: meta-llama/Prompt-Guard-86M + local robust malicious or jailbreak detection.
    Also preserves the logic for private data or forbidden data checks if needed at this stage.
    """
    def __init__(self):
        # Model-based pipeline
        self.tokenizer = AutoTokenizer.from_pretrained("meta-llama/Prompt-Guard-86M")
        self.model = AutoModelForSequenceClassification.from_pretrained("meta-llama/Prompt-Guard-86M")
        self.safety_pipeline = pipeline("text-classification", model=self.model, tokenizer=self.tokenizer)

        # Danger phrases or triggers (including partial “jailbreak” attempts)
        self.danger_phrases = [
            "front-run", "rugpull", "pump scheme", "ponzi", "exploit", "hack", 
            "steal", "drain", "attack", "bypass", "manipulate", "scam", "phish", 
            "honeypot", "trick", "illegal", "backdoor", "malicious", "forge", 
            "spoof", "impersonate", "fake", "avoid kyc", "mixer services", 
            "sandwich attack", "flash loan attack", "steal asset", "drain wallet", 
            "hidden backdoor", "exploit contract", "fake bridge", "fake bridge contract", 
            "fake bridge smart contract", "reentrancy attack", "hidden admin mint functions",
            "jailbreak", "ignore policy", "bypass system", "disable restrictions",
            "infinite mint", "money laundering", "sybil attack", "harvest private key",
            "extract seed phrase", "steal seed phrase", "steal mnemonic"
        ]
        self.instruction_triggers = [
            "how to", "create", "make", "best way to", "guide me", "help me", 
            "instructions to", "steps to", "teach me", "tell me how", "please show me"
        ]

    def fuzzy_replace(self, text: str) -> str:
        """
        Minimal fuzzy approach: replace common numeric or symbolic variants with letters
        for partial match checks.
        """
        replaced = text
        replaced = replaced.replace("0", "o")
        replaced = replaced.replace("1", "i")
        replaced = replaced.replace("3", "e")
        replaced = replaced.replace("@", "a")
        replaced = replaced.replace("$", "s")
        return replaced

    def fuzzy_contains(self, text_lower: str, phrase: str) -> bool:
        if phrase in text_lower:
            return True
        # minimal fuzz:
        replaced = self.fuzzy_replace(text_lower)
        fuzz_phrase = self.fuzzy_replace(phrase)
        if fuzz_phrase in replaced:
            return True
        return False

    def is_suspected_malicious(self, text_lower: str) -> bool:
        # If any danger phrase is found (with mild fuzzy check), consider it suspicious
        for dp in self.danger_phrases:
            if self.fuzzy_contains(text_lower, dp):
                return True
        return False

    def is_instructing_malicious(self, text_lower: str) -> bool:
        # Check if user is instructing (how to, guide me, etc.) + malicious phrase
        if any(instr in text_lower for instr in self.instruction_triggers):
            # Combine with danger
            return True
        return False

    def is_safe_prompt(self, text: str) -> Tuple[bool, float, List[str]]:
        text_lower = text.lower()
        triggered_keywords = []

        # Local robust check
        if self.is_suspected_malicious(text_lower):
            # Gather which phrase triggered
            for dp in self.danger_phrases:
                if self.fuzzy_contains(text_lower, dp):
                    triggered_keywords.append(dp)

            # If also instructing how to do it => immediate reject
            # Or if just any mention => we can forcibly reject to be safe
            # Let's forcibly reject if user mentions any of these. 
            return (False, 1.0, triggered_keywords)

        # 1) meta-llama pipeline check
        outputs = self.safety_pipeline(text, truncation=True)
        label = outputs[0]["label"].upper()  # "SAFE" / "UNSAFE"
        confidence = float(outputs[0]["score"])

        if label == "UNSAFE":
            triggered_keywords.append("meta_llama_guard")
            return (False, 1.0, triggered_keywords)

        # If model says "SAFE" 
        # embed a small safety_score if confidence < 1.0
        safety_score = (1.0 - confidence)*0.2
        return (True, safety_score, triggered_keywords)


###############################################################################
# 2) DomainClassifier with private data, forbidden data, etc.
###############################################################################
class DomainClassifier:
    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(current_dir, "..", "..", "fine_tuned_domain_minilm")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Fine-tuned model path not found at: {model_path}")

        self.model = SentenceTransformer(model_path)

        # Example texts for each category
        self.examples = {
            'blockchain_action': [
                # includes references to personal yields, "my staked assets"
                "Trade 5 MOVE for USDC", "Swap 10 ETH to DAI", "Lend 1000 USDC on Aave",
                "Borrow 50 DAI against ETH collateral", "Send 0.5 BTC to this address",
                "Stake 10 ETH on Lido", "Transfer 20 USDT to my friend",
                "What's my USDC balance?", "How much ETH do I have?",
                "Check my WBTC holdings", "List my staked assets",
                "Display my transaction history", "Show my yield positions",
                "Set up automated compounding for staking rewards",
                "Implement standard ERC20 approve functions",
                "What is my current wallet balance?", "Show me my ETH holdings",
                "What's my current balance?", "Calculate my yearly yield on my holdings"
            ],
            'web3_information': [
                # Non-personal queries about yields, generic info
                "How does Ethereum work?", "Where can I get on-ramped to Polygon network?",
                "What networks do you support?", "What is the price of the BTC token?",
                "Explain how ERC20 tokens function", "How do smart contracts work?",
                "Where can I buy Bitcoin?", "How does proof of stake consensus work?",
                "Show me the liquidity pool amount for USDC/BTC on Uniswap v3",
                "How do I secure my wallet?", "What can you do?", "What is 0G Labs?", "What is Movement Labs?",
                "Give me some examples of what you can do?",
                # DeFi, portfolio, yield (non-personal)
                "Calculate typical yearly yield in DeFi", "What's a typical portfolio value in crypto?",
                "Check the standard liquidation threshold on Aave", "View recommended collateral ratio",
                "Set up automated portfolio rebalancing strategies",
                "Create a liquidity provision strategy for Uniswap",
                # Security info
                "Explain what a recovery phrase is", "What are phishing signs?",
                "How to spot scam tokens?", "How to identify flash loan vulnerabilities?",
                "What is a wallet seed phrase?", "I lost my seed phrase, what should I do?"
            ],
            'private_data': [
                "What is my primary email address?", "I want to update my mailing address to 122 Penn St.",
                "What are my phone numbers?", "Show my stored physical addresses",
                "What is my primary mailing address?", "How many crypto accounts do I have?",
                "What is my date of birth?"
            ],
            'out_of_domain': [
                "How do I bake cookies?",
                "What is the weather tomorrow?",
                "Tell me a joke about cats.",
                "What is the capital of France?"
            ]
        }

        self.example_embeddings = {
            cat: self.model.encode(exs, convert_to_tensor=True)
            for cat, exs in self.examples.items()
        }

        # Private data checks
        self.private_data_terms = [
            'email', 'address', 'addresses', 'phone', 'phones', 'bank name', 'mailing address',
            'primary email', 'primary address', 'account', 'accounts', 'date of birth', 'dob',
            'income', 'annualized income', 'primary phone number'
        ]
        self.forbidden_private_data = [
            'private key', 'seed phrase', 'recovery phrase', 'social security number',
            'ssn', 'passport number', 'national id', 'license number',
            'driver license number', 'bank account number', 'password', 'passwords', 
            'symmetric key', 'mnemonic seed phrase'
        ]

        # Subdomain definitions for web3_information
        self.web3_info_subcategories = {
            "mighty": [
                "mighty network", "mighty sdk", "league on mighty", "sidekicks on mighty", "mighty SDK", "headquarters", "mighty agentic", "mighty league", "secure data vault"
            ],
            "partners": [
                "polygon", "polygon network", "0g labs", "movement labs", "move token",
                "btcOS", "btc", "nillion", "POL", "bitcoinOS"
            ],
            # fallback => "general"
        }

        self.blockchain_action_keywords = [
            "send ", "swap", "trade", "transfer", "bridge", "staking", "unstake",
            "stake", "lend", "borrow", "my wallet", "my staked",
            # Price synonyms (some you might want to keep in separate logic)
            "price", "cost", "going rate", "exchange rate", 
            "my balance", "my holdings", "market cap", "holders", "max supply", "minted supply", "fully diluted",
            "apy", "impermanent loss", "ratio", "volume", "liquidity pool", "price feed", "price feed for",
        ]


    def classify_domain(self, text: str) -> Tuple[str, float]:
        """Return the top domain from your current embedding approach."""
        embedding = self.model.encode(text, convert_to_tensor=True)
        category_scores = {}
        for cat, cat_emb in self.example_embeddings.items():
            sim = cosine_similarity(
                embedding.cpu().numpy().reshape(1, -1),
                cat_emb.cpu().numpy()
            )[0]
            category_scores[cat] = float(np.max(sim))

        best_cat = max(category_scores, key=category_scores.get)
        best_score = category_scores[best_cat]
        return best_cat, best_score

    def classify_subdomain_web3_info(self, text_lower: str) -> str:
        """Your existing subdomain logic: mighty, partners, or general."""
        for subcat, kw_list in self.web3_info_subcategories.items():
            for kw in kw_list:
                if kw in text_lower:
                    return subcat
        return "general"

    def check_blockchain_action_phrases(self, text_lower: str) -> bool:
        """Return True if we see strong 'action' words that should override to blockchain_action."""
        for phrase in self.blockchain_action_keywords:
            if phrase in text_lower:
                return True
        return False

    def _make_domain_result(
        self, 
        categories: List[Tuple[str, float]], 
        subdomain: Optional[str] = None
    ) -> Dict:
        """Helper to build a domain result consistent with pipeline."""
        domain_dict = {
            'is_in_domain': True,
            'needs_clarification': False,
            'category_scores': [
                {'category': cat, 'confidence': conf} for cat, conf in categories
            ],
            'domain_confidence': {
                'highest_crypto_confidence': max(conf for cat, conf in categories),
                'highest_non_crypto_confidence': 0.0
            }
        }
        if subdomain is not None:
            domain_dict['subdomain'] = subdomain

        return {
            'status': 'accepted',
            'safety_score': 0.0,
            'triggered_keywords': [],
            'domain_categories': domain_dict
        }

    def _needs_clarification_result(self) -> Dict:
        return {
            'status': 'needs_clarification',
            'safety_score': 0.0,
            'triggered_keywords': [],
            'reason': 'insufficient_input',
            'ambiguity_type': 'short_prompt',
            'clarification_needed': True
        }
    
    def references_self(self, text_lower: str) -> bool:
        return any(pron in text_lower for pron in ["my ", " mine", " i ", "i want "])

    def is_private_data_request(self, text: str) -> bool:
        text_lower = text.lower()
        if self.references_self(text_lower):
            if any(term in text_lower for term in self.private_data_terms):
                return True
        return False

    def is_forbidden_data_request(self, text: str) -> bool:
        text_lower = text.lower()
        return any(term in text_lower for term in self.forbidden_private_data)

    def classify(self, text: str) -> Dict:
        text_lower = text.strip().lower()

        # 0) Short prompt => needs clarification
        if len(text_lower.split()) < 2:
            return self._needs_clarification_result()

        # 1) If user explicitly requests forbidden private data => reject
        if self.is_forbidden_data_request(text):
            # special check: "what is my private key" => direct reject
            if "what is my private key" in text_lower or "show me my private key" in text_lower:
                return {
                    'status': 'rejected',
                    'reason': 'unsafe_content',
                    'safety_score': 1.0,
                    'triggered_keywords': ['forbidden_private_data']
                }
            # If user is just asking “explain private key,” you might let them pass as info
            # but for now we do a direct rejection if it's not obviously “explain.” 
            if not any(phrase in text_lower for phrase in ["explain", "what is a", "meaning of"]):
                return {
                    'status': 'rejected',
                    'reason': 'unsafe_content',
                    'safety_score': 1.0,
                    'triggered_keywords': ['forbidden_private_data']
                }

        # 2) If user references personal data like bank name, date of birth => private_data
        if self.is_private_data_request(text):
            return self._make_domain_result([('private_data', 0.9)])

        # 3a) Run your embedding-based domain classification
        best_cat, best_score = self.classify_domain(text_lower)

        # 3b) Heuristic override for blockchain_action
        # If any strong “action” words appear, override to blockchain_action
        # *unless* the best_cat is clearly private_data or out_of_domain with very high score, etc.
        # But typically, you can do a simple override:
        if self.check_blockchain_action_phrases(text_lower):
            # If our domain model thinks web3_information is 0.95 but we see the phrase “swap”, 
            # we might override. Or you could do a small threshold.
            # For example:
            if best_cat != 'out_of_domain':
                best_cat = 'blockchain_action'
                best_score = max(best_score, 0.95)

        # 4) Domain-based final
        if best_cat == 'web3_information' and best_score > 0.65:
            subcat = self.classify_subdomain_web3_info(text_lower)
            return self._make_domain_result([('web3_information', best_score)], subdomain=subcat)
        elif best_cat == 'blockchain_action' and best_score > 0.65:
            return self._make_domain_result([('blockchain_action', best_score)])
        elif best_cat == 'private_data' and best_score > 0.65:
            return self._make_domain_result([('private_data', best_score)])
        elif best_cat == 'out_of_domain' and best_score > 0.65:
            return {
                'status': 'rejected',
                'reason': 'out_of_domain',
                'safety_score': 0.0,
                'triggered_keywords': []
            }

        # fallback => out_of_domain
        return {
            'status': 'rejected',
            'reason': 'out_of_domain',
            'safety_score': 0.0,
            'triggered_keywords': []
        }


###############################################################################
# Final: TwoStageClassifier
###############################################################################
class TwoStageClassifier:
    """
    Stage 1: Aggressive MetaGuardSafetyClassifier
    Stage 2: DomainClassifier (with private data checks, forbidden data checks, etc.)
    """
    def __init__(self):
        self.safety_guard = MetaGuardSafetyClassifier()
        self.domain_classifier = DomainClassifier()

    def classify(self, text: str) -> Dict:
        # Step 1: robust safety guard
        is_safe, safety_score, triggered_keywords = self.safety_guard.is_safe_prompt(text)
        if not is_safe:
            return {
                'status': 'rejected',
                'reason': 'unsafe_content',
                'safety_score': safety_score,
                'triggered_keywords': triggered_keywords
            }

        # Step 2: domain classification
        domain_result = self.domain_classifier.classify(text)
        domain_result['safety_score'] = max(domain_result.get('safety_score', 0.0), safety_score)

        if 'triggered_keywords' in domain_result:
            domain_result['triggered_keywords'].extend(triggered_keywords)
        else:
            domain_result['triggered_keywords'] = triggered_keywords

        return domain_result


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

def main():
    try:
        classifier = TwoStageClassifier()
        logger = ResultLogger()

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
            ("Need Clarification", NEED_CLARIFICATION_QUERIES)
        ]

        for category, prompts in categories:
            results = evaluate_results(classifier, prompts, category)
            for result in results:
                logger.log_result(category, result['prompt'], result)

        logger.save()

    except Exception as e:
        print(f"Error in main execution: {str(e)}")


if __name__ == "__main__":
    main()