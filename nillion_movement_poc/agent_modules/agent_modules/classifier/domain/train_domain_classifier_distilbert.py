import os
import json
from pathlib import Path
import random
import torch
import numpy as np

from typing import List
from dataclasses import dataclass
from sklearn.preprocessing import LabelEncoder
from transformers import (
    DistilBertTokenizerFast,
    DistilBertForSequenceClassification,
    Trainer,
    TrainingArguments
)
from torch.utils.data import Dataset

DOMAIN_MODEL_DIR = Path(__file__).resolve().parent.parent / "fine_tuned_domain_distilbert"

@dataclass
class InputExample:
    text: str
    label: int

class DomainDataset(Dataset):
    def __init__(self, examples: List[InputExample], tokenizer: DistilBertTokenizerFast, max_length=128):
        self.examples = examples
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        example = self.examples[idx]
        encodings = self.tokenizer(
            example.text,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        # Flatten the dict of tensors
        input_ids = encodings['input_ids'].squeeze()
        attention_mask = encodings['attention_mask'].squeeze()
        return {
            'input_ids': input_ids,
            'attention_mask': attention_mask,
            'labels': torch.tensor(example.label, dtype=torch.long)
        }

def load_dataset(data_file):
    """
    Expected JSON lines have: {"prompt": "...", "category": "..."}
    """
    texts = []
    labels = []
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                # Remove leading "X|" if present
                if "|" in line:
                    line = line.split("|", 1)[1]
                data = json.loads(line)
                prompt = data["prompt"]
                category = data["category"]
                texts.append(prompt)
                labels.append(category)
            except json.JSONDecodeError:
                continue
    return texts, labels

def train_distilbert_domain_model(
    data_file: str,
    model_name: str = "distilbert-base-uncased",
    output_dir: str = DOMAIN_MODEL_DIR,
    epochs: int = 5,
    batch_size: int = 16
):
    # 1) Load dataset
    texts, labels = load_dataset(data_file)

    # 2) Encode labels
    label_encoder = LabelEncoder()
    numeric_labels = label_encoder.fit_transform(labels)
    label2id = {label: i for i, label in enumerate(label_encoder.classes_)}
    id2label = {i: label for label, i in label2id.items()}
    num_labels = len(label2id)
    print("Domain Classes:", id2label)

    # 3) Create train examples
    examples = [InputExample(t, l) for t, l in zip(texts, numeric_labels)]

    # Shuffle and do a quick train/test split (10% for eval, for example)
    random.shuffle(examples)
    split_idx = int(len(examples) * 0.9)
    train_data = examples[:split_idx]
    eval_data = examples[split_idx:]

    # 4) Initialize tokenizer and model
    tokenizer = DistilBertTokenizerFast.from_pretrained(model_name)
    model = DistilBertForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id
    )

    # 5) Create Dataset objects
    train_dataset = DomainDataset(train_data, tokenizer)
    eval_dataset = DomainDataset(eval_data, tokenizer)

    # 6) Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        logging_dir=os.path.join(output_dir, "logs"),
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True
    )

    # We can define a simple compute_metrics function
    def compute_metrics(eval_pred):
        from sklearn.metrics import accuracy_score
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = accuracy_score(labels, preds)
        return {"accuracy": acc}

    # 7) Define Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics
    )

    # 8) Train
    trainer.train()

    # 9) Save final
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Also save label mappings
    config_path = os.path.join(output_dir, "domain_label_config.json")
    with open(config_path, "w") as f:
        json.dump({
            "label2id": label2id,
            "id2label": {str(k): v for k, v in id2label.items()}
        }, f, indent=2)

    print(f"DistilBERT domain model saved to {output_dir}")

if __name__ == "__main__":
    DATA_FILE = os.path.join(os.path.dirname(__file__), "domain_dataset.jsonl")
    OUTPUT_DIR = DOMAIN_MODEL_DIR
    train_distilbert_domain_model(
        data_file=DATA_FILE,
        model_name="distilbert-base-uncased",
        output_dir=OUTPUT_DIR,
        epochs=5,
        batch_size=16
    )