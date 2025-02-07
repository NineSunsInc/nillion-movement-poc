import os
from datetime import datetime
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from agent_modules.classifier.prompts import (
    STANDARD_FINANCIAL_QUERIES, STANDARD_INFORMATIONAL_QUERIES,
    STANDARD_PRIVATE_VAULT_QUERIES, SAFE_PROMPTS, UNSAFE_PROMPTS, BENIGN_PROMPTS,
    IN_DOMAIN_AND_VAGUE_QUERIES, OUT_OF_DOMAIN_QUERIES, MIXED_PROMPTS, MALICIOUS_PROMPTS
)


@dataclass
class SafetyClassification:
    """
    Data class for safety classification results.
    """
    status: str  # 'accepted', 'rejected', 'needs_clarification'
    safety_score: float
    triggered_keywords: List[Tuple[str, str]]
    reason: Optional[str] = None
    domain_categories: Optional[Dict] = None


class ResultLogger:
    """
    Logger for classification results. Saves results to a JSON file, provides summary statistics,
    and notes potential issues.
    """

    def __init__(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.filename = f'classification_results/results_{timestamp}.json'
        self.results = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'model_version': '1.0',
                'categories_evaluated': [
                    "Safe Prompts",
                    "Benign Prompts",
                    "Unsafe Prompts",
                    "Malicious Prompts",
                    "In-Domain",
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
        """Save the current results to a JSON file, and print a summary of any potential issues."""
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
        """
        Add summary statistics to the results, including acceptance rates,
        rejection rates, and clarification rates per category.
        """
        rejection_reasons = {}
        rejection_keywords = {}

        for category, results in self.results['results_by_category'].items():
            if not results:
                continue

            accepted = sum(1 for r in results if r['status'] == 'accepted')
            rejected = sum(1 for r in results if r['status'] == 'rejected')
            needs_clarification = sum(1 for r in results if r['status'] == 'needs_clarification')
            total = len(results)

            # Analyze rejections
            if rejected > 0:
                category_rejections = [r for r in results if r['status'] == 'rejected']
                reasons = {}
                keywords = set()

                for r in category_rejections:
                    reason = r.get('reason', 'unknown')
                    reasons[reason] = reasons.get(reason, 0) + 1
                    for kw in r.get('triggered_keywords', []):
                        keywords.add(kw[1])

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

        # Add rejection analysis
        self.results['rejection_analysis'] = {
            'reasons_by_category': rejection_reasons,
            'triggered_keywords_by_category': rejection_keywords
        }

    def log_result(self, category, prompt, result):
        """
        Log the classification result for a given prompt under a specified category.
        Also tracks rejected prompts and potential issues.
        """
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

        # Track rejected prompts
        if result.get('status') == 'rejected':
            result_entry.update({
                'reason': result.get('reason', 'unknown'),
                'rejection_details': {
                    'safety_score': result.get('safety_score', 0.0),
                    'triggered_keywords': result.get('triggered_keywords', []),
                    'timestamp': datetime.now().isoformat()
                }
            })
            self.results['rejected_prompts'].append(result_entry)

        # Track ambiguity
        if result.get('status') == 'needs_clarification':
            result_entry['ambiguity_type'] = result.get('ambiguity_type')
            result_entry['clarification_needed'] = result.get('clarification_needed')

        self.results['results_by_category'][category].append(result_entry)

        # Check for potential issues
        self._check_for_issues(prompt, result)

    def _check_for_issues(self, prompt, result):
        """
        Check for potential issues such as high-risk prompts being accepted or
        out-of-domain prompts being accepted.
        """
        if result.get('safety_score', 0.0) > 0.4 and result.get('status') == 'accepted':
            self.results['potential_issues'].append(
                f"High safety score prompt accepted: {prompt}"
            )

        domain_categories = result.get('domain_categories', {})
        if domain_categories.get('is_in_domain') is False and result.get('status') == 'accepted':
            self.results['potential_issues'].append(
                f"Out-of-domain prompt accepted: {prompt}"
            )

        # Check for educational queries not marked as clarification needed
        if any(word in prompt.lower() for word in ['how', 'what', 'why', 'when', 'where']):
            if result.get('status') != 'needs_clarification':
                self.results['potential_issues'].append(
                    f"Educational query marked as ambiguous: {prompt}"
                )


class DomainCategories:
    """
    Classifier for determining if a prompt is within the Web3 domain. Uses keyword
    checks and semantic similarity to identify whether a query is related to crypto,
    blockchain, and related topics.
    """

    def __init__(self):
        self.categories = {
            'web3_actions': {
                'transaction_actions': [
                    'trade', 'swap', 'convert', 'stake', 'unstake',
                    'lend', 'borrow', 'send', 'transfer', 'bridge',
                    'deposit', 'withdraw', 'claim', 'compound', 'compounding', 
                    'approve', 'staking', 'unstaking', 'lending', 'borrowing', 'turn',
                ],
                'query_actions': [
                    'show', 'display', 'list', 'check', 'view',
                    'calculate', 'get', 'what is', "what's", 'find',
                    'track', 'monitor', 'show wallet balance', 'show balance', 
                    'what is my balance', 'what is my wallet balance',
                    'calculate the balance', 'calculate my balance',
                    'what is the price of',
                ]
            },
            'web3_assets': {
                'tokens': [
                    'eth', 'btc', 'usdc', 'usdt', 'move', 'dai',
                    'weth', 'wbtc', 'steth', 'tbtc', 'token', 'crypto',
                ],
                'defi_assets': [
                    'lending position', 'staking position', 'liquidity',
                    'yield', 'rewards', 'portfolio', 'holdings',
                ]
            },
            'web3_context': {
                'wallet_terms': [
                    'wallet', 'balance', 'address', 'transaction',
                    'gas fee', 'network', 'chain',
                ],
                'protocols': [
                    'movement', 'stellar', 'polygon', 'pol', 'bitcoin', 
                    'btc', 'move', 'movement labs', 'polygon pos', 'pol', 'xlm', 'testnet',
                ],
                'defi_terms': [
                    'apy', 'apr', 'tvl', 'pool', 'collateral',
                    'position', 'threshold', 'ratio', 'lending', 'borrowing',
                    'staked', 'staking', 'unstaking', 'liquidity', 'yield', 'yield farming',
                    'cross-chain', 'cross-chain message',
                    'decentralized finance', 'defi', 
                    'bridges', 'bridging', 'multi-chain', 'impermanent loss',
                    'liquidity provider', 'validators', 'erc20', 'erc20 token',
                    'erc721', 'erc721 nft', 'nft', 'erc1155', 'erc1155 nft',
                    'lending platform', 'borrowing platform', 'smart contracts',
                ]
            }
        }

        self.common_non_crypto_assets = [
            'rice', 'grain', 'food', 'card', 'cards', 'pokemon',
            'ball', 'balls', 'gold', 'silver',
            'dollar', 'dollars', 'item', 'items'
        ]

        self.embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')

    def _detect_assets(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Detect crypto and non-crypto assets mentioned in the text.
        """
        text_lower = text.lower()
        words = text_lower.split()

        crypto_assets = []
        for token in self.categories['web3_assets']['tokens']:
            token_lower = token.lower()
            for i, word in enumerate(words):
                if token_lower == word:
                    crypto_assets.append(token)

        non_crypto_assets = []
        for asset in self.common_non_crypto_assets:
            if asset in text_lower:
                non_crypto_assets.append(asset)

        return crypto_assets, non_crypto_assets

    def is_in_domain(self, text: str) -> Dict:
        """
        Determine if the text is within the Web3 domain.

        Returns a dictionary with keys:
        - is_in_domain (bool): True if in domain
        - needs_clarification (bool)
        - category_scores (list of dicts with 'category' and 'confidence')
        - domain_confidence (dict with 'highest_crypto_confidence' and 'highest_non_crypto_confidence')
        """
        text_lower = text.lower()
        scores = {
            'transaction': 0.0,
            'query': 0.0,
            'context': 0.0,
            'assets': 0.0
        }

        # Check for transaction actions
        has_transaction_action = any(
            action in text_lower for action in self.categories['web3_actions']['transaction_actions']
        )
        if has_transaction_action:
            scores['transaction'] = 1.0

        # Check for query actions
        has_query_action = any(
            action in text_lower for action in self.categories['web3_actions']['query_actions']
        )
        if has_query_action:
            scores['query'] = 1.0

        crypto_assets, non_crypto_assets = self._detect_assets(text)

        category_scores = []
        # Check context terms
        for context_type, terms in self.categories['web3_context'].items():
            matches = sum(1 for term in terms if term in text_lower)
            if matches:
                score = matches / len(terms)
                category_scores.append({
                    'category': f'context_{context_type}',
                    'confidence': score
                })
                scores['context'] = max(scores['context'], score)

        # Check assets
        if crypto_assets:
            scores['assets'] = 1.0
            category_scores.append({
                'category': 'asset_tokens',
                'confidence': 1.0
            })

        # Determine if in domain
        is_in_domain = False

        # Transaction scenarios
        if has_transaction_action:
            if crypto_assets and not non_crypto_assets:
                is_in_domain = True
            elif non_crypto_assets:
                # Non-crypto assets with transaction terms considered out-of-domain
                return {
                    'is_in_domain': False,
                    'needs_clarification': False,
                    'category_scores': [{'category': 'invalid_assets', 'confidence': 0.9}],
                    'domain_confidence': {
                        'highest_crypto_confidence': scores['assets'],
                        'highest_non_crypto_confidence': 0.9
                    }
                }

        # Query scenarios
        elif has_query_action:
            # Allow wallet/balance queries without specific tokens
            if any(term in text_lower for term in ['wallet', 'balance', 'holdings', 'portfolio']):
                is_in_domain = True
            elif scores['context'] > 0.2 or crypto_assets:
                is_in_domain = True

        # Context-only scenarios
        elif scores['context'] > 0.5 or (crypto_assets and scores['context'] > 0.2):
            is_in_domain = True

        return {
            'is_in_domain': is_in_domain,
            'needs_clarification': False,
            'category_scores': category_scores,
            'domain_confidence': {
                'highest_crypto_confidence': max(scores.values()),
                'highest_non_crypto_confidence': 0.0 if is_in_domain else 0.9
            }
        }


class TwoStageClassifier:
    """
    A two-stage classifier that first checks for safety (malicious intent, 
    sensitive info requests, etc.) and then checks domain relevance.
    """

    def __init__(self):
        self.domain_categories = DomainCategories()

        # Define unsafe patterns
        self.unsafe_patterns = {
            'exploit_terms': [
                'exploit', 'hack', 'steal', 'drain', 'attack', 'bypass', 'manipulate',
                'fake', 'scam', 'phish', 'honeypot', 'backdoor', 'malicious',
            ],
            'evasion_terms': [
                'avoid', 'evade', 'hide', 'mask', 'bypass', 'clone', 'impersonate',
                'fake', 'forge', 'spoof', 'obscure',
            ],
            'sensitive_data': [
                'private key', 'seed phrase', 'recovery phrase', 'password',
                'credentials', 'secret', 'mnemonic', 'bank account', 'social security number',
                'ssn', 'password number', 'national id', 'license number', 'driver license number',
            ]
        }

        # Define clear patterns that shouldn't need clarification
        self.clear_patterns = {
            'balance_queries': [
                'my balance', 'my holdings', 'my portfolio',
                'my wallet', 'my assets', 'my funds', 'my wallets'
            ],
            'price_queries': [
                'price of', 'gas fee', 'exchange rate',
                'conversion rate', 'current price',
                'liquidity', 'liquidity pool', 'token price', 'token value'
            ],
            'network_queries': [
                'supported networks', 'available chains',
                'which blockchain', 'what networks',
                'what network', 'network status'
            ]
        }

        # Define patterns that indicate ambiguity
        self.ambiguous_patterns = {
            'general_terms': [
                'it', 'that', 'this', 'they', 'them',
                'something', 'anything', 'everything',
                'somewhere', 'anywhere', 'everywhere'
            ],
            'needs_context': [
                'how much', 'which one', 'what time',
                'when', 'where', 'who', 'whose', 'why',
                'what', 'which', 'which is what', 'which is which',
                'how can it be', 'who did it'
            ]
        }

        # Define safe informational patterns
        self.safe_info_patterns = {
            'balance_queries': [
                'balance', 'holdings', 'portfolio', 'wallet', 'assets',
                'how much', 'what is my', "what's my", 'show me', 'display',
                'amount', 'total holding', 'total holdings', 'total assets'
            ],
            'educational_queries': [
                'how does', 'what is', 'explain', 'tell me about', 'help me understand',
                'how do i', 'what are', 'show me how'
            ],
            'price_queries': [
                'price', 'value', 'worth', 'cost', 'fee', 'gas', 'rate', 'exchange rate',
                'conversion rate', 'current price', 'current value', 'token price',
                'liquidity', 'liquidity pool', 'liquidity provider',
                'slippage'
            ]
        }

    def classify(self, text: str) -> Dict:
        """
        Classify a given prompt text into one of:
        - accepted (safe and in-domain)
        - rejected (unsafe or out-of-domain)
        - needs_clarification (safe but ambiguous)
        """
        # Stage 1: Safety Check
        safety_result = self._check_safety(text)
        if not safety_result['is_safe']:
            return {
                'status': 'rejected',
                'reason': 'unsafe_content',
                'safety_score': safety_result['safety_score'],
                'triggered_keywords': safety_result['triggered_keywords']
            }

        text_lower = text.lower()
        # Check if it's a safe informational query first
        info_query_type = self._check_info_query(text_lower)
        if info_query_type:
            return {
                'status': 'accepted',
                'safety_score': 0.0,
                'triggered_keywords': [],
                'domain_categories': {
                    'is_in_domain': True,
                    'needs_clarification': False,
                    'category_scores': [
                        {'category': info_query_type, 'confidence': 1.0}
                    ],
                    'domain_confidence': {
                        'highest_crypto_confidence': 1.0,
                        'highest_non_crypto_confidence': 0.0
                    }
                }
            }

        # Domain Classification
        domain_result = self.domain_categories.is_in_domain(text)
        if not domain_result['is_in_domain']:
            return {
                'status': 'rejected',
                'reason': 'out_of_domain',
                'safety_score': 0.0,
                'triggered_keywords': [],
                'domain_categories': domain_result
            }

        # Check for ambiguity
        ambiguity_result = self._check_ambiguity(text)
        if ambiguity_result.get('is_ambiguous', False):
            return {
                'status': 'needs_clarification',
                'safety_score': 0.0,
                'triggered_keywords': [],
                'ambiguity_type': ambiguity_result.get('ambiguity_type', 'general'),
                'clarification_needed': ambiguity_result.get('clarification_needed', ''),
                'domain_categories': domain_result
            }

        return {
            'status': 'accepted',
            'safety_score': 0.0,
            'triggered_keywords': [],
            'domain_categories': domain_result
        }

    def _check_safety(self, text: str) -> Dict:
        """
        Check if the input is safe by looking for unsafe patterns.
        """
        text_lower = text.lower()
        triggered_keywords = []

        for category, patterns in self.unsafe_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    triggered_keywords.append(pattern)

        safety_score = len(triggered_keywords) * 0.1
        return {
            'is_safe': (len(triggered_keywords) == 0),
            'safety_score': safety_score,
            'triggered_keywords': triggered_keywords
        }

    def _check_info_query(self, text: str) -> Optional[str]:
        """
        Check if the input is a safe informational query related to domain concepts.
        """
        for category, patterns in self.safe_info_patterns.items():
            if any(pattern in text for pattern in patterns):
                # Validate for balance queries
                if category == 'balance_queries':
                    if any(term in text for term in ['wallet', 'balance', 'holdings', 'portfolio']):
                        return 'wallet_query'
                # Validate for educational queries
                elif category == 'educational_queries':
                    # Ensure no unsafe terms
                    if not any(u in text for u in self.unsafe_patterns['exploit_terms']):
                        return 'educational_query'
                # Validate for price queries
                elif category == 'price_queries':
                    if any(token.lower() in text for token in self.domain_categories.categories['web3_assets']['tokens']):
                        return 'price_query'
        return None

    def _check_ambiguity(self, text: str) -> Dict:
        """
        Check if the query is ambiguous and may need clarification.
        """
        text_lower = text.lower()

        # Clear patterns check
        for _, patterns in self.clear_patterns.items():
            if any(pattern in text_lower for pattern in patterns):
                return {'is_ambiguous': False}

        # Ownership check
        has_ownership = 'my' in text_lower or 'mine' in text_lower
        if has_ownership and any(word in text_lower for word in ['balance', 'wallet', 'holdings', 'portfolio']):
            return {'is_ambiguous': False}

        # Check for general ambiguity
        general_ambiguous = any(term in text_lower.split() for term in self.ambiguous_patterns['general_terms'])
        context_needed = any(term in text_lower for term in self.ambiguous_patterns['needs_context'])

        if general_ambiguous or context_needed:
            clarification_type = []
            if general_ambiguous:
                clarification_type.append('general')
            if context_needed:
                clarification_type.append('context')

            return {
                'is_ambiguous': True,
                'ambiguity_type': '_'.join(clarification_type),
                'clarification_needed': self._generate_clarification_prompt(clarification_type)
            }

        return {'is_ambiguous': False}

    def _generate_clarification_prompt(self, clarification_types: List[str]) -> str:
        """
        Generate a clarification prompt based on the type of ambiguity.
        """
        if 'general' in clarification_types:
            return "Could you please be more specific about what you're referring to?"
        if 'context' in clarification_types:
            return "Could you provide more context about what you're asking?"
        return "Could you please clarify your request?"


def evaluate_results(classifier, prompts, category_name):
    """
    Evaluate and print the classification results for a set of prompts under a given category.
    Also returns the results for logging.
    """
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
                print("Triggered Keywords:")
                for keyword in result['triggered_keywords']:
                    print(f"  • {keyword}")

        if result['status'] == 'accepted':
            domain_results = result.get('domain_categories', {})
            if domain_results:
                print("\nDomain Categories:")
                for score in domain_results.get('category_scores', []):
                    print(f"  • {score['category']}: {score['confidence']:.3f}")
                print(f"Is In-Domain: {domain_results.get('is_in_domain', False)}")
                print("Domain Confidence:")
                confidence = domain_results.get('domain_confidence', {})
                print(f"  Highest Crypto Confidence: {confidence.get('highest_crypto_confidence', 0.0):.3f}")
                print(f"  Highest Non-Crypto Confidence: {confidence.get('highest_non_crypto_confidence', 0.0):.3f}")

    # Print category summary
    print(f"\n{category_name} Summary:")
    print(f"Total Prompts: {len(prompts)}")
    print(f"Rejected: {rejected_count} ({(rejected_count/len(prompts))*100:.1f}%)")
    if rejection_reasons:
        print("\nRejection Reasons:")
        for reason, count in rejection_reasons.items():
            print(f"  • {reason}: {count}")

    return results


def main():
    """
    Main execution function. Evaluates multiple categories of prompts and logs the results.
    """
    try:
        classifier = TwoStageClassifier()
        logger = ResultLogger()

        categories = [
            ("Safe Prompts", SAFE_PROMPTS),
            ("Benign Prompts", BENIGN_PROMPTS),
            ("Unsafe Prompts", UNSAFE_PROMPTS),
            ("Malicious Prompts", MALICIOUS_PROMPTS),
            ('In-Domain', IN_DOMAIN_AND_VAGUE_QUERIES),
            ("Mixed Prompts", MIXED_PROMPTS),
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