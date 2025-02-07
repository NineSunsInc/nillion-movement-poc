import os
from datetime import datetime
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# just top domains and no subcategories.

# Improvements in this version:
# 1. Keep the original three categories: blockchain_action, web3_information, private_data.
# 2. Within web3_information, we introduce subcategories (not as separate return values, but as
#    conceptual guidance for logic):
#    - security_info: questions about recovery phrases, phishing, scams, vulnerabilities, but
#      only if educational or protective in nature.
#    - general_info: questions about yields, portfolio value, liquidity, etc.
#
# 3. Safety checks refined:
#    - Distinguish between asking for sensitive data directly (e.g. "What's my private key?")
#      versus asking for educational info about seed phrases or recovery phrases ("What is a wallet seed phrase?")
#    - Educational questions about safety and security are allowed.
#    - Requests for malicious actions ("How to front-run transactions?", "How to rugpull?", "How to make ponzi smart contract?")
#      are rejected as unsafe_content due to malicious intent.
#
# 4. Domain classification improvements:
#    - Add more examples under web3_information to cover portfolio queries, yield calculations, liquidation thresholds,
#      and other DeFi-related info.
#    - If a prompt strongly matches web3_information or blockchain_action, accept.
#    - If unsure, consider "needs_clarification" for borderline cases (not implemented in-depth here, but demonstrated as a concept).
#
# 5. Out-of-domain and unsafe checks remain, but we now have more nuanced heuristics for malicious requests.
#
# 6. Future-proof by providing more diverse examples and flexible logic.

from agent_modules.classifier.prompts import (
    STANDARD_FINANCIAL_QUERIES, STANDARD_INFORMATIONAL_QUERIES,
    STANDARD_PRIVATE_VAULT_QUERIES, SAFE_PROMPTS, UNSAFE_PROMPTS, BENIGN_PROMPTS,
    IN_DOMAIN_AND_VAGUE_QUERIES, OUT_OF_DOMAIN_QUERIES, MIXED_PROMPTS, MALICIOUS_PROMPTS
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

        self.filename = os.path.join(current_dir, '..', '..', 'classification_results', 'subcategorization_tests', f'ft_out_domain_before_{timestamp}.json')

        self.results = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'model_version': '3.0',
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
                    "Standard Private Vault Prompts"
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


class DomainClassifier:
    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(current_dir, "..", "..", "fine_tuned_domain_minilm")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Fine-tuned model path not found at: {model_path}")
        self.model = SentenceTransformer(model_path)

        # Expanded examples to cover more web3 information scenarios, including portfolio management,
        # yields, security questions (educational), and general queries.
        self.examples = {
            'blockchain_action': [
                "Trade 5 MOVE for USDC",
                "Swap 10 ETH to DAI",
                "Lend 1000 USDC on Aave",
                "Borrow 50 DAI against ETH collateral",
                "Send 0.5 BTC to this address",
                "Stake 10 ETH on Lido",
                "Transfer 20 USDT to my friend",
                "What's my USDC balance?",
                "How much ETH do I have?",
                "Check my WBTC holdings",
                "List my active positions",
                "Display my transaction history",
                "Set up automated compounding for staking rewards",
                "Implement standard ERC20 approve functions",
                "What is my current wallet balance?",
                "Show me my ETH holdings",
                "What's my current balance?"
            ],
            'web3_information': [
                # General info
                "How does Ethereum work?",
                "Where can I get on-ramped to Polygon network?",
                "What networks do you support?",
                "What is the price of the BTC token?",
                "Explain how ERC20 tokens function",
                "How do smart contracts work?",
                "Where can I buy Bitcoin?",
                "How does proof of stake consensus work?",
                "Show me the liquidity pool amount for USDC/BTC on Uniswap v3",
                "How do I secure my wallet?",
                "What can you do?",
                "What is 0G Labs?",
                "What is Movement Labs?",
                "Give me some examples of what you can do?",
                # Portfolio and DeFi info (general subcategory)
                "Calculate my yearly yield",
                "What's my total portfolio value?",
                "Check my liquidation threshold",
                "View my collateral ratio (on Aave)",
                "Calculate optimal gas fees across multiple chains",
                "Set up automated portfolio rebalancing",
                "Create a liquidity provision strategy",
                # Security info subcategory
                "Explain what a recovery phrase is",
                "What are phishing signs?",
                "How to spot scam tokens?",
                "How to identify flash loan vulnerabilities?",
                "What is a wallet seed phrase?",
                "I lost my seed phrase, what should I do?"
            ],
            'private_data': [
                "What is my primary email address?",
                "I want to update my mailing address to 122 Penn St.",
                "What are my phone numbers?",
                "Show my stored physical addresses",
                "What is my primary mailing address?",
                "How many crypto accounts do I have?",
                "What is my date of birth?",
            ]
        }

        self.example_embeddings = {
            cat: self.model.encode(exs, convert_to_tensor=True)
            for cat, exs in self.examples.items()
        }

        self.blockchain_actions = [
            'trade', 'swap', 'convert', 'stake', 'unstake',
            'lend', 'borrow', 'send', 'transfer', 'bridge',
            'deposit', 'withdraw', 'claim', 'farm', 'reinvest', 'buy', 'sell',
            'compound', 'implement', 'approve', 'sign message', 'positions', 'transaction history', 'balance', 'holdings'
        ]

        self.private_data_terms = [
            'email', 'address', 'addresses', 'phone', 'phones', 'bank name', 'mailing address',
            'primary email', 'primary address', 'account', 'accounts', 'date of birth', 'dob', 'income', 'annualized income', 
            'primary email address', 'primary phone number'
        ]

        self.forbidden_private_data = [
            'private key', 'seed phrase', 'recovery phrase', 'social security number', 'ssn',
            'passport number', 'national id', 'license number', 'driver license number', 'bank account number', 'password', 'passwords', 
            'symmetric key', 'mnemonic seed phrase'
        ]

        # Now we will refine the handling of these terms. Educational queries about these terms are allowed.
        # Direct requests for disclosure of personal credentials or keys are not allowed.

        self.supported_crypto_tokens = [
            'eth', 'btc', 'usdc', 'usdt', 'dai', 'move', 'weth', 'wbtc', 'steth', 'tbtc', 'sepoliaeth', 'wpol'
        ]

        self.web3_keywords = [
            'ethereum', 'polygon', 'bitcoin', 'btc', 'eth', 'smart contract', 'dapp', 'defi',
            'uniswap', 'aave', 'erc20', 'proof of stake', 'onramp', 'staking', 'token', 'mighty network',
            '0g labs', 'movement labs', 'stellar', 'nillion', 'avalanche', '0g', 'portals.fi', 'beefy', 'movement', 'move', 'testnet', 'yields'
        ]

        # Malicious or exploit-related terms that indicate unsafe content if the user asks for instructions:
        self.malicious_intent_keywords = [
            'front-run', 'rugpull', 'pump scheme', 'ponzi', 'exploit', 'hack', 'steal',
            'drain', 'attack', 'bypass', 'manipulate', 'scam', 'phish', 'honeypot', 'backdoor', 'malicious', 'forge',
            'spoof', 'impersonate', 'fake', 'avoid kyc', 'mixer services'
        ]

    def classify_domain(self, text: str) -> Tuple[str, float]:
        embedding = self.model.encode(text, convert_to_tensor=True)
        category_scores = {}
        for cat, cat_emb in self.example_embeddings.items():
            sim = cosine_similarity(embedding.cpu().numpy().reshape(1, -1), cat_emb.cpu().numpy())[0]
            category_scores[cat] = float(np.max(sim))

        best_cat = max(category_scores, key=category_scores.get)
        best_score = category_scores[best_cat]
        return best_cat, best_score

    def _references_self(self, text_lower: str) -> bool:
        return any(pron in text_lower for pron in ["my ", " my", "mine", "i ", " i"])

    def is_forbidden_private_data(self, text: str) -> bool:
        # We'll treat "private key", "seed phrase", "recovery phrase" differently now.
        # Only forbidden if user tries to reveal or ask for the actual sensitive data from the system.
        # Just mentioning them in an educational way shouldn't be a direct rejection.
        text_lower = text.lower()
        # Remove seed phrase and recovery phrase from direct forbidden checks here;
        # handle them contextually later.
        forbidden_strict = [
            'private key', 'social security number', 'ssn', 'passport number',
            'national id', 'license number', 'driver license number', 'bank account number', 'password', 'passwords',
            'symmetric key', 'mnemonic seed phrase'
        ]
        return any(term in text_lower for term in forbidden_strict)

    def is_private_data_request(self, text: str) -> bool:
        text_lower = text.lower()
        if self._references_self(text_lower):
            if any(term in text_lower for term in self.private_data_terms):
                return True
        return False

    def is_balance_inquiry(self, text: str) -> bool:
        text_lower = text.lower()
        if self._references_self(text_lower):
            if "balance" in text_lower or "holdings" in text_lower or "my wallet" in text_lower:
                return True
            if "how much" in text_lower:
                return True
        return False

    def is_blockchain_action(self, text: str) -> bool:
        text_lower = text.lower()
        if any(action in text_lower for action in self.blockchain_actions):
            return True
        if self.is_balance_inquiry(text):
            return True
        if self._references_self(text_lower) and any(kw in text_lower for kw in ["transaction history", "active positions", "wallet balance", "eth holdings", "crypto holdings"]):
            return True
        if "erc20" in text_lower and "approve" in text_lower:
            return True
        return False

    def has_unsupported_assets(self, text: str) -> bool:
        text_lower = text.lower()
        unsupported_terms = ['pokemon card', 'pokemon cards', 'rice', 'grain', 'grains']
        return any(u in text_lower for u in unsupported_terms)

    def is_malicious_intent(self, text: str) -> bool:
        # If user asks "how to front-run" or "best way to rugpull" - it's malicious.
        text_lower = text.lower()
        # Distinguish between educational queries about security and malicious instructions
        # If user says "How to front-run transactions?" - malicious
        # If user says "Explain what front-running is" - educational
        # We'll consider queries starting with "how to" or "best way to" + malicious keyword as malicious intent.
        # Also "create pump schemes", "make ponzi", "avoid kyc" - malicious.
        # More robust rule: If user asks "how to" + malicious term = reject
        # If user says "show vulnerabilities" - ambiguous, but we consider "show flash loan vulnerabilities" might be educational.
        # We'll rely on explicit malicious action phrasing:
        malicious_phrases = [
            "how to front-run", "front-run transactions", "how to rugpull", "how to create pump schemes",
            "how to make ponzi", "how to avoid kyc", "best mixer services?"  # mixers are often used for illicit reasons but not always
        ]
        # We'll treat mixers as suspicious but not always malicious. We can let mixers pass for now since user might just ask info.
        # But we must handle pump scheme, ponzi, rugpull as malicious.

        # Check for malicious intent:
        # If the user asks "how to" + any malicious keyword
        # malicious keywords:
        malicious_keywords_for_instructions = ['front-run', 'rugpull', 'pump scheme', 'ponzi', 'exploit', 'hack', 'steal', 'drain', 'attack']
        # We'll also consider "how to avoid kyc" malicious since it's evading regulations.
        if any(mk in text_lower for mk in malicious_keywords_for_instructions):
            # If query suggests instructions: "how to", "best way to", "create", "make"
            if any(phrase in text_lower for phrase in ["how to", "best way to", "create", "make"]):
                return True
            # If it says "show ... backdoor methods" is also malicious instructions (helping malicious action)
            if "show" in text_lower and ("backdoor" in text_lower or "vulnerabilities" in text_lower and "exploit" in text_lower):
                return True

        # If user just says "show flash loan vulnerabilities" - It's ambiguous.
        # We'll allow educational unless it explicitly says "how to exploit flash loan vulnerabilities".
        # "Show flash loan vulnerabilities" could be educational (security research).
        # For strictness, let's allow showing vulnerabilities (info), but if "how to exploit" is mentioned, reject.
        if "how to exploit" in text_lower:
            return True

        # "Avoid kyc"
        if "avoid kyc" in text_lower:
            return True

        return False

    def is_sensitive_seed_reveal(self, text: str) -> bool:
        # Distinguish between asking for explanation vs. asking for the assistant to reveal user's own sensitive keys.
        # If user says: "Where can I find my recovery phrase?" -> Educational or a request for instructions. Allowed.
        # If user says: "What is a wallet seed phrase?" -> Just asking definition. Allowed.
        # If user says: "Show me my seed phrase" -> Trying to get the model to produce it. Not allowed.
        # If user says: "Give me my recovery phrase." -> Not allowed.
        text_lower = text.lower()
        if "seed phrase" in text_lower or "recovery phrase" in text_lower:
            # Check if user is asking for direct disclosure:
            if any(x in text_lower for x in ["give me my", "what is my", "show me my", "where is my"]):
                return True
            # If user says "I lost my seed phrase, what do I do?" - This is educational/helpful, allowed.
            # If user says "What is a wallet seed phrase?" - allowed.
            # If user says "Where can I find my recovery phrase to restore my wallet?" 
            # This might mean: how to retrieve it from their backup. It's allowed as educational guidance.
            # We'll allow these kinds of queries since the assistant is not actually revealing a stored key.
        return False

    def classify(self, text: str) -> Dict:
        text_lower = text.lower()

        # Check if malicious intent:
        if self.is_malicious_intent(text):
            return {
                'status': 'rejected',
                'reason': 'unsafe_content',
                'safety_score': 0.1,
                'triggered_keywords': ['malicious_intent']
            }

        # Safety check for truly forbidden data requests (e.g., private keys)
        if self.is_forbidden_private_data(text):
            # Check if user is asking for actual keys from the system:
            # If just explaining what a private key is -> allowed
            # If "what is my private key" -> This tries to retrieve user-specific sensitive info. Reject.
            if "what is my private key" in text_lower or "show me my private key" in text_lower:
                return {
                    'status': 'rejected',
                    'reason': 'unsafe_content',
                    'safety_score': 0.1,
                    'triggered_keywords': ['forbidden_private_data']
                }
            # If just "Explain what a private key is"
            if "explain" in text_lower or "what is a" in text_lower:
                # It's educational, let it pass as web3 info (security_info)
                pass
            else:
                # Conservative: If it's about retrieving a known forbidden data directly
                return {
                    'status': 'rejected',
                    'reason': 'unsafe_content',
                    'safety_score': 0.1,
                    'triggered_keywords': ['forbidden_private_data']
                }

        # Check seed phrase or recovery phrase requests more carefully:
        if ("seed phrase" in text_lower or "recovery phrase" in text_lower) and self.is_sensitive_seed_reveal(text):
            # If user tries to get their actual seed phrase from the system
            return {
                'status': 'rejected',
                'reason': 'unsafe_content',
                'safety_score': 0.1,
                'triggered_keywords': ['forbidden_private_data']
            }

        # If it's just asking about what a seed phrase is, or what to do if lost,
        # treat it as educational web3 info (security_info) and accept.

        # Private data request
        if self.is_private_data_request(text):
            return self._make_domain_result([('private_data', 0.9)])

        # Blockchain action
        if self.is_blockchain_action(text):
            if self.has_unsupported_assets(text):
                return {
                    'status': 'rejected',
                    'reason': 'unsupported_assets',
                    'safety_score': 0.0,
                    'triggered_keywords': []
                }
            return self._make_domain_result([('blockchain_action', 0.9)])

        # Web3 Information
        best_cat, best_score = self.classify_domain(text)
        # Use a reasonable threshold
        if best_cat == 'web3_information' and best_score > 0.65:
            return self._make_domain_result([('web3_information', best_score)])
        elif best_cat == 'blockchain_action' and best_score > 0.65:
            # fallback if a prompt better matches blockchain_action
            return self._make_domain_result([('blockchain_action', best_score)])
        elif best_cat == 'private_data' and best_score > 0.65:
            return self._make_domain_result([('private_data', best_score)])

        # If we reach here, it's likely out-of-domain or very uncertain.
        # Instead of rejecting immediately, we can choose to "needs_clarification".
        # But the user requested to keep original logic as much as possible. We'll reject as out_of_domain to maintain original logic.
        return {
            'status': 'rejected',
            'reason': 'out_of_domain',
            'safety_score': 0.0,
            'triggered_keywords': []
        }

    def _make_domain_result(self, categories: List[Tuple[str, float]]) -> Dict:
        return {
            'status': 'accepted',
            'safety_score': 0.0,
            'triggered_keywords': [],
            'domain_categories': {
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
        }


class TwoStageClassifier:
    def __init__(self):
        self.domain_classifier = DomainClassifier()

        # We'll refine unsafe patterns to more explicitly handle malicious intent
        self.unsafe_patterns = {
            'exploit_terms': [
                'exploit', 'hack', 'steal', 'drain', 'attack', 'bypass', 'manipulate',
                'fake', 'scam', 'phish', 'honeypot', 'backdoor', 'malicious', 'forge', 'spoof', 'impersonate'
            ],
            'evasion_terms': [
                'avoid', 'evade', 'hide', 'mask', 'bypass', 'clone', 'fake', 'forge', 'spoof', 'impersonate'
            ],
            'sensitive_data': [
                'private key', 'seed phrase', 'recovery phrase', 'password',
                'credentials', 'secret', 'mnemonic', 'bank account', 'social security number',
                'ssn', 'passport number', 'national id', 'license number', 'driver license number'
            ]
        }

    def classify(self, text: str) -> Dict:
        # We'll rely on domain classifier for final logic.
        # Safety check is integrated there, but we can do a preliminary check here as well.
        safety_result = self._check_safety(text)
        if not safety_result['is_safe']:
            return {
                'status': 'rejected',
                'reason': 'unsafe_content',
                'safety_score': safety_result['safety_score'],
                'triggered_keywords': safety_result['triggered_keywords']
            }

        domain_result = self.domain_classifier.classify(text)
        return domain_result

    def _check_safety(self, text: str) -> Dict:
        # Basic keyword detection: If terms appear that we consider suspicious, raise safety_score.
        # Domain classifier now handles more nuance, but we keep this as a fallback.
        text_lower = text.lower()
        triggered_keywords = []
        all_unsafe = (self.unsafe_patterns['exploit_terms']
                      + self.unsafe_patterns['evasion_terms']
                      + self.unsafe_patterns['sensitive_data'])
        for pattern in all_unsafe:
            if pattern in text_lower:
                triggered_keywords.append(pattern)

        # If triggered_keywords found, we raise safety_score, but not always reject here because the domain classifier
        # might accept educational queries about these terms.
        safety_score = len(triggered_keywords) * 0.1
        # is_safe = no triggered keywords or we rely on domain logic for final decision
        # We'll say it's is_safe, but domain classifier might still reject if malicious.
        # This gives domain_classifier final say.
        return {
            'is_safe': True,
            'safety_score': safety_score,
            'triggered_keywords': triggered_keywords
        }


def evaluate_results(classifier, prompts, category_name):
    results = []
    print(f"\nEvaluating {category_name}:")
    print("=" * 80)
    rejected_count = 0
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

        if result['status'] == 'accepted':
            domain_results = result.get('domain_categories', {})
            if domain_results:
                print("\nDomain Categories:")
                for score in domain_results.get('category_scores', []):
                    print(f"  • {score['category']}: {score['confidence']:.3f}")
                print(f"Is In-Domain: {domain_results.get('is_in_domain', False)}")

    print(f"\n{category_name} Summary:")
    print(f"Total Prompts: {len(prompts)}")
    print(f"Rejected: {rejected_count} ({(rejected_count/len(prompts))*100:.1f}%)")
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
            ("Standard Private Vault Prompts", STANDARD_PRIVATE_VAULT_QUERIES)
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