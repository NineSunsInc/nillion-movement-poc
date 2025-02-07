import os
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class SafetyClassification:
    status: str
    safety_score: float
    triggered_keywords: List[str]
    reason: Optional[str] = None
    domain_categories: Optional[Dict] = None


class DomainClassifier:
    def __init__(self):
        # Load model
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(current_dir, "..", "..", "fine_tuned_domain_minilm")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Fine-tuned model path not found at: {model_path}")
        self.model = SentenceTransformer(model_path)

        # Added queries like "What can you do?" and "What networks do you support?" to web3_information examples
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
                "Implement standard ERC20 approve functions with spending caps",
                "What is my current wallet balance?",
                "What is my complete wallet balance?",
                "Show me my ETH holdings",
                "What's my current balance?"
            ],
            'web3_information': [
                "How does Ethereum work?",
                "Where can I get onramped to Polygon network?",
                "What is Mighty Network?",
                "What is the price of the BTC token?",
                "Explain how ERC20 tokens function",
                "How do smart contracts work?",
                "Where can I buy Bitcoin?",
                "What networks do you support?",
                "How does proof of stake consensus work?",
                "Show me the liquidity pool amount for USDC/BTC on Uniswap v3",
                "How do I secure my wallet?",
                "What can you do?",
                "What is 0G Labs?",
                "What is Movement Labs?",
                "Give me some examples of what you can do?"
            ],
            'private_data': [
                "What is my primary email address?",
                "I want to update my mailing address to 122 Penn St.",
                "What are my phone numbers?",
                "Show my stored physical addresses",
                "What is my primary mailing address?",
                "How many crypto accounts do I have?"
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
            'compound', 'implement', 'approve'
        ]

        self.private_data_terms = [
            'email', 'address', 'addresses', 'phone', 'phones', 'bank name', 'mailing address',
            'primary email', 'primary address', 'account', 'accounts'
        ]

        self.forbidden_private_data = [
            'private key', 'seed phrase', 'recovery phrase', 'social security number', 'ssn',
            'passport number', 'national id', 'license number', 'driver license number', 'bank account'
        ]

        self.supported_crypto_tokens = [
            'eth', 'btc', 'usdc', 'usdt', 'dai', 'move', 'weth', 'wbtc', 'steth', 'tbtc'
        ]

        # Web3 keywords (no longer mandatory for web3_information if similarity is high)
        self.web3_keywords = [
            'ethereum', 'polygon', 'bitcoin', 'btc', 'eth', 'smart contract', 'dapp', 'defi',
            'uniswap', 'aave', 'erc20', 'proof of stake', 'onramp', 'staking', 'token', 'mighty network',
            '0g labs', 'movement labs', 'stellar', 'nillion', 'avalanche'
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
        text_lower = text.lower()
        return any(term in text_lower for term in self.forbidden_private_data)

    def is_private_data_request(self, text: str) -> bool:
        text_lower = text.lower()
        if self._references_self(text_lower):
            return any(term in text_lower for term in self.private_data_terms)
        return False

    def is_balance_inquiry(self, text: str) -> bool:
        text_lower = text.lower()
        if self._references_self(text_lower):
            if "balance" in text_lower or "holdings" in text_lower:
                return True
            if "how much" in text_lower:
                return True
            if "my wallet" in text_lower or "current wallet balance" in text_lower:
                return True
        return False

    def is_blockchain_action(self, text: str) -> bool:
        text_lower = text.lower()

        if any(action in text_lower for action in self.blockchain_actions):
            return True

        if self.is_balance_inquiry(text):
            return True

        if self._references_self(text_lower) and any(kw in text_lower for kw in ["transaction history", "active positions", "wallet balance", "eth holdings"]):
            return True

        if "erc20" in text_lower and "approve" in text_lower:
            return True

        if "compounding for staking rewards" in text_lower or "staking rewards" in text_lower:
            return True

        return False

    def has_unsupported_assets(self, text: str) -> bool:
        text_lower = text.lower()
        unsupported_terms = ['pokemon card', 'pokemon cards', 'rice', 'grain', 'grains']
        return any(u in text_lower for u in unsupported_terms)

    def classify(self, text: str) -> Dict:
        text_lower = text.lower()

        # Safety check
        if self.is_forbidden_private_data(text):
            return {
                'status': 'rejected',
                'reason': 'unsafe_content',
                'safety_score': 0.1,
                'triggered_keywords': ['forbidden_private_data']
            }

        # Private data
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

        # Web3 information: Now we accept if >0.7 similarity, no need for web3_keywords strictly
        best_cat, best_score = self.classify_domain(text)
        if best_cat == 'web3_information' and best_score > 0.7:
            return self._make_domain_result([('web3_information', best_score)])

        # Otherwise out-of-domain
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

        self.unsafe_patterns = {
            'exploit_terms': [
                'exploit', 'hack', 'steal', 'drain', 'attack', 'bypass', 'manipulate',
                'fake', 'scam', 'phish', 'honeypot', 'backdoor', 'malicious'
            ],
            'evasion_terms': [
                'avoid', 'evade', 'hide', 'mask', 'bypass', 'clone', 'impersonate',
                'fake', 'forge', 'spoof', 'obscure'
            ],
            'sensitive_data': [
                'private key', 'seed phrase', 'recovery phrase', 'password',
                'credentials', 'secret', 'mnemonic', 'bank account', 'social security number',
                'ssn', 'passport number', 'national id', 'license number', 'driver license number'
            ]
        }

    def classify(self, text: str) -> Dict:
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
        text_lower = text.lower()
        triggered_keywords = []
        all_unsafe = (self.unsafe_patterns['exploit_terms']
                      + self.unsafe_patterns['evasion_terms']
                      + self.unsafe_patterns['sensitive_data'])
        for pattern in all_unsafe:
            if pattern in text_lower:
                triggered_keywords.append(pattern)

        safety_score = len(triggered_keywords) * 0.1
        return {
            'is_safe': (len(triggered_keywords) == 0),
            'safety_score': safety_score,
            'triggered_keywords': triggered_keywords
        }
