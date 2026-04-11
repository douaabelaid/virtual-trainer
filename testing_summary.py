"""
testing_summary.py - Aggregate User Testing Results

Combines individual user test JSON files into an overall summary report.

Usage:
    python testing_summary.py user_test_*.json
    python testing_summary.py user_test_User1_*.json user_test_User2_*.json user_test_User3_*.json
"""

import argparse
import json
import statistics
from pathlib import Path
from typing import List, Dict


def load_test_results(filenames: List[str]) -> List[Dict]:
    """Load all user test JSON files"""
    results = []
    for filename in filenames:
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                results.append(data)
                print(f"✓ Loaded: {filename}")
        except Exception as e:
            print(f"✗ Error loading {filename}: {e}")
    return results


def generate_overall_summary(results: List[Dict]) -> Dict:
    """Generate overall summary across all users"""
    
    if not results:
        return {}
    
    # Collect metrics across all users
    accuracies = []
    latencies = []
    all_feedback = []
    meets_target = []
    latency_ok = []
    
    for result in results:
        summary = result.get('summary', {})
        accuracies.append(summary.get('overall_rep_accuracy', 0))
        latencies.append(summary.get('average_mean_latency', 0))
        all_feedback.extend(summary.get('all_feedback_flags', []))
        meets_target.append(summary.get('meets_90_percent_target', False))
        latency_ok.append(summary.get('latency_under_100ms', True))
    
    avg_accuracy = statistics.mean(accuracies) if accuracies else 0
    avg_latency = statistics.mean(latencies) if latencies else 0
    unique_feedback = list(set(all_feedback))
    all_users_90_percent = all(meets_target)
    all_latency_under_100 = all(latency_ok)
    
    return {
        'total_users_tested': len(results),
        'average_rep_accuracy_percent': avg_accuracy,
        'average_latency_ms': avg_latency,
        'all_users_meet_90_percent': all_users_90_percent,
        'latency_consistently_under_100ms': all_latency_under_100,
        'unique_feedback_flags': unique_feedback,
        'ready_for_demo': all_users_90_percent and all_latency_under_100 and len(results) >= 3,
    }


def print_individual_results(results: List[Dict]):
    """Print table for each user"""
    
    for i, result in enumerate(results, 1):
        user_info = result.get('user_info', {})
        sets = result.get('sets', [])
        summary = result.get('summary', {})
        
        print(f"\n{'='*80}")
        print(f"USER {i}")
        print(f"{'='*80}")
        print(f"Name / Initials:  {user_info.get('name', 'N/A')}")
        print(f"Height (cm):      {user_info.get('height_cm', 'N/A')}")
        print(f"Age:              {user_info.get('age', 'N/A')}")
        print(f"Date & Time:      {user_info.get('date_time', 'N/A')}")
        print(f"Exercise tested:  {user_info.get('exercise', 'N/A')}")
        print()
        
        # Set-by-set table
        print(f"{'Metric':<35} {'Set 1':>12} {'Set 2':>12}")
        print(f"{'-'*35} {'-'*12} {'-'*12}")
        
        s1 = sets[0] if len(sets) >= 1 else {}
        s2 = sets[1] if len(sets) >= 2 else {}
        
        print(f"{'Actual reps performed':<35} {s1.get('actual_reps', 'N/A'):>12} {s2.get('actual_reps', 'N/A'):>12}")
        print(f"{'Reps counted by system':<35} {s1.get('reps_counted', 'N/A'):>12} {s2.get('reps_counted', 'N/A'):>12}")
        
        acc1 = f"{s1['rep_accuracy']:.1f}%" if 'rep_accuracy' in s1 else 'N/A'
        acc2 = f"{s2['rep_accuracy']:.1f}%" if 'rep_accuracy' in s2 else 'N/A'
        print(f"{'Rep accuracy (%)':<35} {acc1:>12} {acc2:>12}")
        
        lat1 = f"{s1['mean_latency']:.1f}" if 'mean_latency' in s1 else 'N/A'
        lat2 = f"{s2['mean_latency']:.1f}" if 'mean_latency' in s2 else 'N/A'
        print(f"{'Mean latency (ms)':<35} {lat1:>12} {lat2:>12}")
        
        max1 = f"{s1['max_latency']:.1f}" if 'max_latency' in s1 else 'N/A'
        max2 = f"{s2['max_latency']:.1f}" if 'max_latency' in s2 else 'N/A'
        print(f"{'Max latency (ms)':<35} {max1:>12} {max2:>12}")
        
        over1 = 'Y' if s1.get('any_latency_over_100', False) else 'N' if s1 else 'N/A'
        over2 = 'Y' if s2.get('any_latency_over_100', False) else 'N' if s2 else 'N/A'
        print(f"{'Any latency > 100ms? (Y/N)':<35} {over1:>12} {over2:>12}")
        
        det1 = 'Y' if s1.get('landmarks_detection_rate', 0) > 50 else 'N' if s1 else 'N/A'
        det2 = 'Y' if s2.get('landmarks_detection_rate', 0) > 50 else 'N' if s2 else 'N/A'
        print(f"{'Landmarks detected? (Y/N)':<35} {det1:>12} {det2:>12}")
        
        # Feedback flags
        flags1 = ', '.join(s1.get('feedback_flags', [])) if s1.get('feedback_flags') else 'None'
        flags2 = ', '.join(s2.get('feedback_flags', [])) if s2.get('feedback_flags') else 'None'
        print(f"{'Feedback flags triggered':<35} {flags1[:12]:>12} {flags2[:12]:>12}")
        
        print()
        print(f"Threshold adjustments needed?  {'Yes - see notes' if summary.get('all_feedback_flags') else 'No'}")
        print(f"Notes / Observations:          Overall accuracy {summary.get('overall_rep_accuracy', 0):.1f}%")


def print_overall_summary(summary: Dict):
    """Print the overall summary table"""
    
    print(f"\n{'='*80}")
    print(f"OVERALL SUMMARY")
    print(f"{'='*80}")
    print()
    print(f"{'Question':<60} {'Answer':>18}")
    print(f"{'-'*60} {'-'*18}")
    
    print(f"{'Average rep accuracy across all users (%)':<60} {summary['average_rep_accuracy_percent']:>18.1f}")
    print(f"{'Average latency across all users (ms)':<60} {summary['average_latency_ms']:>18.1f}")
    print(f"{'Did all {n} users meet 90% rep accuracy target?'.format(n=summary['total_users_tested']):<60} {('YES' if summary['all_users_meet_90_percent'] else 'NO'):>18}")
    print(f"{'Was latency consistently under 100ms?':<60} {('YES' if summary['latency_consistently_under_100ms'] else 'NO'):>18}")
    
    feedback_str = ', '.join(summary['unique_feedback_flags']) if summary['unique_feedback_flags'] else 'No'
    print(f"{'Threshold adjustments needed for squat?':<60} {feedback_str[:18]:>18}")
    
    ready = 'YES ✓' if summary['ready_for_demo'] else 'NO ✗'
    print(f"{'Ready for final demo? (Y/N)':<60} {ready:>18}")
    
    print(f"\n{'='*80}")
    
    # Detailed readiness check
    print(f"\nReadiness Checklist:")
    print(f"  ☑ Users tested: {summary['total_users_tested']}/3 {'✓' if summary['total_users_tested'] >= 3 else '✗ (need more)'}")
    print(f"  {'☑' if summary['all_users_meet_90_percent'] else '☐'} Rep accuracy ≥90%: {'✓' if summary['all_users_meet_90_percent'] else '✗'}")
    print(f"  {'☑' if summary['latency_consistently_under_100ms'] else '☐'} Latency <100ms: {'✓' if summary['latency_consistently_under_100ms'] else '✗'}")
    print()


def main():
    parser = argparse.ArgumentParser(description='Aggregate User Testing Results')
    parser.add_argument('files', nargs='+', help='JSON files from user_testing.py')
    parser.add_argument('--output', type=str, help='Save summary to this JSON file (optional)')
    
    args = parser.parse_args()
    
    print("="*80)
    print("USER TESTING SUMMARY REPORT")
    print("="*80)
    print()
    
    # Load all test results
    results = load_test_results(args.files)
    
    if not results:
        print("\n✗ No valid test results found!")
        return
    
    print(f"\n✓ Loaded {len(results)} user test(s)\n")
    
    # Print individual results
    print_individual_results(results)
    
    # Generate and print overall summary
    summary = generate_overall_summary(results)
    print_overall_summary(summary)
    
    # Save to file if requested
    if args.output:
        output_data = {
            'generated_at': str(Path(__file__).resolve()),
            'individual_results': results,
            'overall_summary': summary,
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\n✓ Summary saved to: {args.output}")


if __name__ == '__main__':
    main()
