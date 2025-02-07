import json
import os
import argparse
from typing import Dict, List, Optional
from datetime import datetime

class ResultsComparator:
    """Compares two classifier result files and shows differences"""
    
    def __init__(self, new_results_file: str, old_results_file: str):
        self.new_file_name = os.path.basename(new_results_file)
        self.old_file_name = os.path.basename(old_results_file)
        
        with open(new_results_file) as f:
            self.new_results = json.load(f)
        with open(old_results_file) as f:
            self.old_results = json.load(f)

    def _convert_to_bool(self, value) -> bool:
        """Convert various truth values to Python bool"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == 'true'
        return bool(value)

    def compare(self) -> Dict:
        """Compare two result sets and return differences"""
        changes = []
        stats = {
            "total_prompts": 0,
            "matching_results": 0,
            "different_results": 0,
            "status_changes": 0,
            "domain_changes": 0,
            "category_changes": 0,
            "confidence_changes": 0,
            "subdomain_changes": 0,
            "subdomain_stats": {},
            "subdomain_percentages": {},
            # Add status stats
            "status_stats": {
                "accepted": 0,
                "rejected": 0,
                "out_of_domain": 0
            },
            "status_percentages": {}
        }
        
        # Compare all categories
        for category in self.new_results["results_by_category"]:
            new_prompts = self.new_results["results_by_category"][category]
            old_prompts = self.old_results["results_by_category"].get(category, [])
            
            # Track status stats
            for prompt in new_prompts:
                if prompt["status"] == "accepted":
                    stats["status_stats"]["accepted"] += 1
                elif prompt["status"] == "rejected":
                    stats["status_stats"]["rejected"] += 1
                
                # Check domain status
                if "domain_categories" in prompt:
                    is_in_domain = self._convert_to_bool(prompt["domain_categories"].get("is_in_domain", False))
                    if not is_in_domain:
                        stats["status_stats"]["out_of_domain"] += 1

            # Track subdomain stats
            for prompt in new_prompts:
                if "domain_categories" in prompt:
                    subdomain = prompt["domain_categories"].get("subdomain", "none")
                    stats["subdomain_stats"][subdomain] = stats["subdomain_stats"].get(subdomain, 0) + 1

            # Calculate percentages
            total = len(new_prompts)
            if total > 0:
                stats["status_percentages"] = {
                    "accepted": (stats["status_stats"]["accepted"] / total) * 100,
                    "rejected": (stats["status_stats"]["rejected"] / total) * 100,
                    "out_of_domain": (stats["status_stats"]["out_of_domain"] / total) * 100
                }
            
            # Calculate subdomain percentages
            if total > 0:
                stats["subdomain_percentages"] = {
                    subdomain: (count / total) * 100 
                    for subdomain, count in stats["subdomain_stats"].items()
                }

            # Create lookup dict for old prompts
            old_prompt_dict = {p["prompt"]: p for p in old_prompts}
            
            for new_prompt in new_prompts:
                prompt_text = new_prompt["prompt"]
                stats["total_prompts"] += 1
                
                if prompt_text not in old_prompt_dict:
                    changes.append({
                        "prompt": prompt_text,
                        "type": "new_prompt",
                        "category": category
                    })
                    stats["different_results"] += 1
                    continue
                
                old_prompt = old_prompt_dict[prompt_text]
                differences = {}
                
                # Compare status
                if new_prompt["status"] != old_prompt["status"]:
                    differences["status"] = {
                        "old": old_prompt["status"],
                        "new": new_prompt["status"]
                    }
                    stats["status_changes"] += 1
                
                # Compare domain categories if present
                if "domain_categories" in new_prompt and "domain_categories" in old_prompt:
                    new_domain = new_prompt["domain_categories"]
                    old_domain = old_prompt["domain_categories"]
                    
                    # Convert is_in_domain to bool for comparison
                    new_is_in_domain = self._convert_to_bool(new_domain.get("is_in_domain", False))
                    old_is_in_domain = self._convert_to_bool(old_domain.get("is_in_domain", False))
                    
                    if new_is_in_domain != old_is_in_domain:
                        differences["domain_status"] = {
                            "old": old_is_in_domain,
                            "new": new_is_in_domain
                        }
                        stats["domain_changes"] += 1
                    
                    # Compare categories and confidences
                    if "category_scores" in new_domain and "category_scores" in old_domain:
                        new_cats = {c["category"]: c["confidence"] for c in new_domain["category_scores"]}
                        old_cats = {c["category"]: c["confidence"] for c in old_domain["category_scores"]}
                        
                        if new_cats.keys() != old_cats.keys():
                            differences["categories"] = {
                                "old": list(old_cats.keys()),
                                "new": list(new_cats.keys())
                            }
                            stats["category_changes"] += 1
                        else:
                            # Compare confidences
                            conf_changes = {}
                            for cat in new_cats:
                                if abs(new_cats[cat] - old_cats[cat]) > 0.1:  # 10% threshold
                                    conf_changes[cat] = {
                                        "old": old_cats[cat],
                                        "new": new_cats[cat]
                                    }
                            if conf_changes:
                                differences["confidences"] = conf_changes
                                stats["confidence_changes"] += 1
                
                # Compare subdomains if present
                if "domain_categories" in new_prompt and "domain_categories" in old_prompt:
                    new_subdomain = new_prompt["domain_categories"].get("subdomain", "none")
                    old_subdomain = old_prompt["domain_categories"].get("subdomain", "none")
                    
                    if new_subdomain != old_subdomain:
                        differences["subdomain"] = {
                            "old": old_subdomain,
                            "new": new_subdomain
                        }
                        stats["subdomain_changes"] += 1

                if differences:
                    changes.append({
                        "prompt": prompt_text,
                        "category": category,
                        "differences": differences
                    })
                    stats["different_results"] += 1
                else:
                    stats["matching_results"] += 1
        
        return {
            "changes": changes,
            "stats": stats,
            "metadata": {
                "new_file": self.new_file_name,
                "old_file": self.old_file_name,
                "timestamp": datetime.now().isoformat()
            }
        }

    def print_comparison_report(self):
        """Print a human-readable comparison report"""
        comparison = self.compare()
        
        print("\n" + "="*80)
        print("CLASSIFIER RESULTS COMPARISON REPORT")
        print("="*80)
        
        print(f"\nComparing files:")
        print(f"NEW: {self.new_file_name}")
        print(f"OLD: {self.old_file_name}")
        
        # Print status statistics
        print("\nSTATUS STATISTICS:")
        print("-"*80)
        stats = comparison["stats"]
        total = stats["total_prompts"]
        
        print(f"Total prompts: {total}")
        print(f"Accepted: {stats['status_stats']['accepted']} ({stats['status_percentages']['accepted']:.1f}%)")
        print(f"Rejected: {stats['status_stats']['rejected']} ({stats['status_percentages']['rejected']:.1f}%)")
        print(f"Out of Domain: {stats['status_stats']['out_of_domain']} ({stats['status_percentages']['out_of_domain']:.1f}%)")
        
        print("\nDIFFERENCES FOUND:")
        print("-"*80)
        
        if not comparison["changes"]:
            print("No differences found in matching prompts!")
        else:
            for change in comparison["changes"]:
                print(f"\nPrompt: \"{change['prompt']}\"")
                print(f"Category: {change['category']}")
                
                if "type" in change and change["type"] == "new_prompt":
                    print("  NEW PROMPT")
                    continue
                
                for diff_type, details in change["differences"].items():
                    if diff_type == "status":
                        print(f"  Status:")
                        print(f"    OLD ({self.old_file_name}): {details['old']}")
                        print(f"    NEW ({self.new_file_name}): {details['new']}")
                    
                    elif diff_type == "domain_status":
                        print(f"  Domain Status:")
                        print(f"    OLD ({self.old_file_name}): {details['old']}")
                        print(f"    NEW ({self.new_file_name}): {details['new']}")
                    
                    elif diff_type == "categories":
                        print(f"  Categories:")
                        print(f"    OLD ({self.old_file_name}): {', '.join(details['old'])}")
                        print(f"    NEW ({self.new_file_name}): {', '.join(details['new'])}")
                    
                    elif diff_type == "confidences":
                        print(f"  Confidence Scores:")
                        for cat, values in details.items():
                            print(f"    {cat}:")
                            print(f"      OLD ({self.old_file_name}): {values['old']:.3f}")
                            print(f"      NEW ({self.new_file_name}): {values['new']:.3f}")
                            if "subdomain" in values:
                                print(f"      Subdomain:")
                                print(f"        OLD: {values.get('old_subdomain', 'none')}")
                                print(f"        NEW: {values.get('new_subdomain', 'none')}")
        
        print("\n" + "="*80)
        print("STATISTICS")
        print("="*80)
        
        print(f"\nTotal prompts compared:     {stats['total_prompts']}")
        print(f"Matching results:           {stats['matching_results']}")
        print(f"Different results:          {stats['different_results']}")
        print(f"Status changes:             {stats['status_changes']}")
        print(f"Domain changes:             {stats['domain_changes']}")
        print(f"Category changes:           {stats['category_changes']}")
        print(f"Confidence changes:         {stats['confidence_changes']}")
        print(f"Subdomain changes:          {stats['subdomain_changes']}")
        
        # Print subdomain statistics
        print("\nSUBDOMAIN STATISTICS:")
        print("-"*80)
        for subdomain, count in stats["subdomain_stats"].items():
            percentage = stats["subdomain_percentages"][subdomain]
            print(f"{subdomain}: {count} ({percentage:.1f}%)")
        
        print("\n" + "="*80)

    def save_comparison(self, output_path: str) -> str:
        """Run comparison and save results to file"""
        comparison = self.compare()
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Create output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(
            output_path, 
            os.path.join(current_dir, f"eval/comparison_{timestamp}.json")
        )
        
        # Create directory if it doesn't exist
        os.makedirs(output_path, exist_ok=True)
        
        # Save comparison results
        with open(output_file, 'w') as f:
            json.dump(comparison, f, indent=2)
        
        # Print the human-readable report
        self.print_comparison_report()
        
        return output_file

def main():
    parser = argparse.ArgumentParser(description='Compare two classifier result files')
    parser.add_argument('new_file', help='Path to new results file')
    parser.add_argument('old_file', help='Path to old results file')
    parser.add_argument('--output', '-o', 
                       default='classification_results/comparisons',
                       help='Output directory for comparison results')
    
    args = parser.parse_args()
    
    comparator = ResultsComparator(args.new_file, args.old_file)
    output_file = comparator.save_comparison(args.output)
    
    print(f"\nComparison saved to: {output_file}")
    
    # Print summary stats
    comparison = comparator.compare()
    stats = comparison["stats"]
    print("\nComparison Summary:")
    print(f"Total prompts compared: {stats['total_prompts']}")
    print(f"Total differences found: {stats['different_results']}")
    print(f"Status changes: {stats['status_changes']}")
    print(f"Domain category changes: {stats['domain_changes']}")
    print(f"Category changes: {stats['category_changes']}")
    print(f"Confidence changes: {stats['confidence_changes']}")

if __name__ == "__main__":
    main() 