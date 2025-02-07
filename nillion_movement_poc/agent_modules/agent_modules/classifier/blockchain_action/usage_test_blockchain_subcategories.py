from agent_modules.classifier.blockchain_action.ft_blockchain_actions_classifier import BlockchainActionClassifier
from agent_modules.classifier.blockchain_action.blockchain_action_subcat_test import test_blockchain_subcategories

if __name__ == "__main__":
    model_dir = "./distilbert_blockchain_action"
    classifier = BlockchainActionClassifier(model_dir)
    test_blockchain_subcategories(classifier)