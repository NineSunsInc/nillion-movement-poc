import json
import os
from sklearn.preprocessing import LabelEncoder
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

# Configuration
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DATA_FILE = os.path.join(os.path.dirname(__file__), "domain_dataset.jsonl")

# This will be saved in the python/chat_ui/fine_tuned_all_minilm directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fine_tuned_domain_minilm")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_dataset(data_file):
    examples = []
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:  # Skip empty lines
                continue
            try:
                # Remove any line numbers if present (e.g., "1|" at start of line)
                if "|" in line:
                    line = line.split("|", 1)[1]
                data = json.loads(line)
                prompt = data["prompt"]
                category = data["category"]
                examples.append((prompt, category))
            except json.JSONDecodeError as e:
                print(f"Skipping invalid JSON line: {line}")
                continue
    return examples

def main():
    # Load dataset
    data = load_dataset(DATA_FILE)
    
    # Extract texts and labels
    texts = [d[0] for d in data]
    labels = [d[1] for d in data]

    # Encode labels to integers
    label_encoder = LabelEncoder()
    numeric_labels = label_encoder.fit_transform(labels)
    label_classes = list(label_encoder.classes_)
    num_labels = len(label_classes)
    print("Number of classes:", num_labels, label_classes)

    # Load the sentence transformer model
    model = SentenceTransformer(MODEL_NAME)

    # Each InputExample now has texts=[txt, txt] to provide two embeddings
    train_examples = [InputExample(texts=[txt, txt], label=lbl) for txt, lbl in zip(texts, numeric_labels)]

    # Create a DataLoader
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)

    # Pass the single-sentence embedding dimension only (384)
    # By default, SoftmaxLoss with all concatenations enabled will expand this to 1536 internally.
    loss = losses.SoftmaxLoss(
        model=model,
        sentence_embedding_dimension=model.get_sentence_embedding_dimension(),
        num_labels=num_labels
        # Keep defaults: concatenation_sent_rep=True, concatenation_sent_difference=True, concatenation_sent_multiplication=True
    )

    # Train the model
    model.fit(
        train_objectives=[(train_dataloader, loss)],
        epochs=13,
        warmup_steps=int(0.1 * len(train_dataloader)),
        output_path=OUTPUT_DIR
    )

    print(f"Model fine-tuned and saved at: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()