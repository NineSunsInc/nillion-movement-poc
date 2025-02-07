# Classifiers Playground

A comprehensive framework for training and running domain and blockchain action classifiers using DistilBERT models.

## Overview

This project contains two main classification components:

1. Domain Classifier - Determines if input belongs to blockchain/web3 domain
2. Blockchain Action Classifier - Categorizes specific blockchain actions (trade, send, etc.)

The unified test framework combines both classifiers for end-to-end classification.

## Installation

### Requirements

- Python 3.8+
- PyTorch 1.8+
- Transformers 4.5+
- Sentence Transformers 2.0+
- scikit-learn

### Setup

1. Clone the repository:

```bash
git clone https://github.com/NineSunsInc/mock-poc.git
cd chat_ui/modules/classifier
```

2. Create and activate virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Project Structure

```
modules/classifier
├── README.md
├── action_classifier.py
├── blockchain_action
│   ├── blockchain_action_dataset.jsonl
│   ├── blockchain_action_subcat_test.py
│   ├── finetune_blockchain_actions.py
│   ├── ft_blockchain_actions_classifier.py
│   └── usage_test_blockchain_subcategories.py
├── classifier.py
├── dataset.jsonl
├── domain
│   ├── domain_action_classifier.py
│   ├── domain_dataset.jsonl
│   ├── domains_test_prompts.py
│   ├── ft_action_classifier_OLD.py
│   ├── ft_domain_action_classifier_v2.py
│   ├── ft_domain_action_classifier_v3.py
│   ├── train_domain_classifier_distilbert.py
│   └── train_v6_top_domains_sections.py
├── eval/
├── eval_unified_tests.py
├── ft_action_classifier.py
├── ft_action_classifier_v2.py
├── prompts.py
├── requirements.txt
├── results/
├── run_unified_tests.py
├── run_unified_tests_v3.py
└── train_v6_top_domains_sections.py
```

## Training Models

### 1. Domain Classifier

Train the domain classifier using DistilBERT on the `modules/classifier/domain directory`:

```bash
python train_domain_classifier_distilbert.py
```

This will:

- Load training data from `domain_dataset.jsonl`
- Fine-tune DistilBERT model
- Save model to `fine_tuned_domain_distilbert/`

### 2. Blockchain Action Classifier

Train the blockchain action classifier in the `modules/classifier/blockchain_action directory`:

```bash
python finetune_blockchain_actions.py \
    --train_file ./blockchain_action/blockchain_action_dataset.jsonl \
    --model_output_dir ../../fine_tuned_blockchain_action
```

This will:

- Load training data from `blockchain_action_dataset.jsonl`
- Fine-tune model for blockchain action classification
- Save model to `fine_tuned_blockchain_action/`

## Running Classifiers

### Individual Classifiers

1. Domain Classifier:

```bash
python ./domain/ft_domain_action_classifier_v3.py \
    --model_dir ../../fine_tuned_domain_distilbert \
    --prompt "Your test prompt here"
```

2. Blockchain Action Classifier:

```bash
python ./blockchain_action/ft_blockchain_actions_classifier.py \
    --model_dir ../../fine_tuned_blockchain_action \
    --prompt "Your test prompt here"
```

### Unified Testing

Run both classifiers together using the unified test framework:

```bash
python ./run_unified_tests_v3.py
```

This will:

1. Load both trained models
2. Run test prompts through both classifiers
3. Output results to `python/chat_ui/classification_results/subcategorization_tests/`

Results are saved as JSON files with timestamp, containing:

- Classification results by category
- Rejected prompts
- Safety scores
- Domain categories
- Blockchain action subcategories

## Output Format

Results are saved in JSON format:

```json
{
  "timestamp": "...",
  "results_by_category": {
    "Safe Prompts": [...],
    "Unsafe Prompts": [...],
    "Benign Prompts": [...],
    "Mixed Prompts": [...],
    "Blockchain Action Trade": [...]
  },
  "rejected_prompts": [...],
  "metrics": {
    "accuracy": ...,
    "precision": ...,
    "recall": ...
  }
}
```

## Model Files

The project uses Git LFS for managing large model files:

```
*.pt filter=lfs diff=lfs merge=lfs -text
*.safetensors filter=lfs diff=lfs merge=lfs -text
```

Make sure to install Git LFS before cloning the repository (via `brew install git-lfs`).

# Classifier Results Comparator

A tool for comparing classifier results between different model versions.

## Installation

No additional installation required beyond the main project dependencies.

## Usage

### Basic Comparison

```bash
python eval_unified_tests.py <new_file> <old_file>
```

Example:
```bash
python eval_unified_tests.py \
    ../../classification_results/subcategorization_tests/ft_unified_v5.3_20250113_004415.json \
    ../../classification_results/subcategorization_tests/ft_unified_classifiers_v4_20250112_183257.json
```

### Custom Output Directory

```bash
python eval_unified_tests.py \
    --output /path/to/output \
    <new_file> <old_file>
```

# Classifier Results Comparator

## Usage

### 1. Running New Tests

Generate new test results:
```bash
python run_unified_tests_v3.py
```

This will:
- Run all test categories
- Save results to timestamped file in `python/chat_ui/classification_results/subcategorization_tests/`
- Display the path to saved results

### 2. Running Tests with Comparison

Generate new results and compare with previous version:
```bash
python run_unified_tests_v3.py --compare-with ../../classification_results/subcategorization_tests/ft_unified_v5_20250112_191026.json
```

This will:
- Run all test categories
- Save new results
- Compare with specified previous results
- Generate comparison report
- Save detailed comparison to `eval/comparison_[timestamp].json`

### 3. Comparing Existing Results

To compare two existing result files:
```bash
python eval_unified_tests.py <new_file> <old_file>
```

Example:
```bash
python eval_unified_tests.py \
    ../../classification_results/subcategorization_tests/ft_unified_v5.3_20250113_145623.json \
    ../../classification_results/subcategorization_tests/ft_unified_v5_20250112_191026.json
```

## Output Format

The comparison report shows:
1. File Information:
   - Names of new and old files being compared
   
2. Status Statistics:
   - Total prompts analyzed
   - Acceptance/rejection rates
   - Out-of-domain percentages

3. Detailed Changes:
   - Category changes
   - Confidence score differences
   - Subdomain updates
   - Status changes

4. Summary Statistics:
   - Total differences found
   - Breakdown by change type
   - Domain and category shifts

## Notes

1. Confidence changes are only reported if they differ by more than 10%
2. Subdomain information is tracked for:
   - web3_information categories
   - blockchain_action categories
3. Status statistics show the distribution of:
   - Accepted prompts
   - Rejected prompts
   - Out-of-domain prompts