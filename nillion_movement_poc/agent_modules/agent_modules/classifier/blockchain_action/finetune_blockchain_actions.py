"""
finetune_blockchain_actions.py

Usage example:
    python finetune_blockchain_actions.py \
        --train_file ./blockchain_action_dataset.jsonl \
        --model_output_dir ./distilbert_blockchain_action \
        --num_train_epochs 3 \
        --batch_size 16
"""
import json
import os
from pathlib import Path
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    DataCollatorWithPadding,
    DistilBertConfig,
    DistilBertForSequenceClassification,
    Trainer,
    TrainingArguments,
    EarlyStoppingCallback
)
from evaluate import load as load_metric
from torch.utils.data import DataLoader

# Configuration
MODEL_NAME = "distilbert-base-uncased"
DATA_FILE = Path(__file__).resolve().parent / "blockchain_action_dataset.jsonl"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "fine_tuned_blockchain_action"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

def filter_and_map_categories(example):
    # Only keep prompts whose categories are in this valid set.
    valid_cats = [
        "token_price", "token_query", "pair_price", "pair_query",
        "trade", "send", "cross_chain", "wallet_balance"
    ]
    return example["category"] in valid_cats

def map_labels_to_int(example, label2id):
    # Map string labels to integer indices.
    example["labels"] = label2id[example["category"]]
    return example

def main():
    # Load dataset from JSONL file
    dataset = load_dataset("json", data_files={"train": str(DATA_FILE)})
    
    # Filter categories
    dataset["train"] = dataset["train"].filter(filter_and_map_categories)
    
    # Create label mappings
    unique_labels = sorted(set(dataset["train"]["category"]))
    label2id = {lab: i for i, lab in enumerate(unique_labels)}
    id2label = {i: lab for lab, i in label2id.items()}
    print(f"Label mapping: {label2id}")
    
    # Optional: Shuffle the entire training dataset before we do the train_test_split
    dataset["train"] = dataset["train"].shuffle(seed=42)
    
    # Load model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    config = DistilBertConfig.from_pretrained(
        MODEL_NAME, 
        num_labels=len(label2id),
        id2label=id2label,
        label2id=label2id
    )
    model = DistilBertForSequenceClassification.from_pretrained(MODEL_NAME, config=config)

    # Prepare dataset by mapping labels to integer IDs
    dataset["train"] = dataset["train"].map(lambda ex: map_labels_to_int(ex, label2id))
    
    # Tokenize prompts (batched for efficiency)
    tokenized_dataset = dataset["train"].map(
        lambda examples: tokenizer(examples["prompt"], truncation=True),
        batched=True
    )

    # Split into training and evaluation sets
    train_test = tokenized_dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset = train_test["train"]
    eval_dataset = train_test["test"]

    print(f"Train set size: {len(train_dataset)}, Eval set size: {len(eval_dataset)}")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        # If you want more frequent eval to catch overfitting early, set "steps" here:
        evaluation_strategy="epoch",
        save_strategy="epoch",
        num_train_epochs=13,
        learning_rate=1e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        logging_dir=os.path.join(OUTPUT_DIR, "logs"),
        logging_steps=50,
        load_best_model_at_end=True,
        metric_for_best_model="eval_f1",
        greater_is_better=True,
        save_total_limit=3,
        seed=42,
        data_seed=42,
    )

    # Metrics setup
    accuracy_metric = load_metric("accuracy")
    f1_metric = load_metric("f1")

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        predictions = logits.argmax(axis=-1)
        acc = accuracy_metric.compute(predictions=predictions, references=labels)
        f1 = f1_metric.compute(predictions=predictions, references=labels, average="weighted")
        return {
            "accuracy": acc["accuracy"],
            "f1": f1["f1"]
        }

    # If you want to manually create a DataLoader to ensure shuffling, you can do so:
    # train_dataloader = DataLoader(
    #     train_dataset,
    #     batch_size=training_args.per_device_train_batch_size,
    #     shuffle=True  # ensures each epoch sees samples in a different order
    # )

    # But typically, Trainer handles that for you automatically.

    # Initialize Trainer with EarlyStopping
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset.remove_columns(["prompt","category"]),
        eval_dataset=eval_dataset.remove_columns(["prompt","category"]),
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)]
    )

    # Train the model
    trainer.train()
    
    # Save final model
    trainer.save_model(OUTPUT_DIR)
    
    # Save label mapping
    with open(os.path.join(OUTPUT_DIR, "label_mapping.json"), "w") as f:
        json.dump({"label2id": label2id, "id2label": id2label}, f, indent=2)

    print(f"Model saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()