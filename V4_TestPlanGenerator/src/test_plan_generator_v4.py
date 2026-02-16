#!/usr/bin/env python3
"""
V4 Test Plan Generator - Orchestrator

Imports all modules and runs the complete V4 pipeline:
  Module 1: Build Z3 model from questionnaire JSON
  Module 2: Enumerate valid assignments (3-phase approach)
  Module 3: Validate assignments
  Module 4: Generate test plan output

Usage:
    python test_plan_generator_v4.py <questionnaire_json> [output_dir]
"""

import json
import sys
import os
from pathlib import Path

from module1_constraint_builder import build_z3_model
from module2_enumeration import enumerate_valid_assignments
from module3_validator import validate_assignment
from module4_output_generator import generate_test_plan_output


def greedy_set_cover(valid_assignments, all_reachable_questions):
    """
    Greedy set cover: select minimal test cases to cover all questions.
    
    Args:
        valid_assignments: List of dicts with 'visible_questions' key
        all_reachable_questions: Set of all question numbers to cover
    
    Returns:
        List of selected test cases (dicts with 'number', 'assignment', 'visible_questions', 'question_count')
    """
    uncovered = set(all_reachable_questions)
    selected = []
    test_case_num = 1
    
    while uncovered:
        # Find assignment that covers the most uncovered questions
        best_assignment = None
        best_coverage = 0
        best_visible = set()
        
        for assignment in valid_assignments:
            visible = set(assignment['visible_questions'])
            coverage = len(visible & uncovered)
            
            if coverage > best_coverage:
                best_coverage = coverage
                best_assignment = assignment
                best_visible = visible
        
        if best_assignment is None:
            break  # No more assignments can cover remaining questions
        
        # Add this assignment to selected test cases
        selected.append({
            'number': test_case_num,
            'assignment': best_assignment['assignment'],
            'complete_assignment': best_assignment['complete_assignment'],
            'visible_questions': best_assignment['visible_questions'],
            'question_count': len(best_assignment['visible_questions'])
        })
        
        # Remove covered questions
        uncovered -= best_visible
        test_case_num += 1
        
        # Remove this assignment so we don't select it again
        valid_assignments.remove(best_assignment)
    
    return selected


def main():
    # Parse arguments
    if len(sys.argv) < 2:
        print("=" * 80)
        print("V4 Test Plan Generator")
        print("=" * 80)
        print()
        print("Usage: python test_plan_generator_v4.py <questionnaire_json> [output_dir]")
        print()
        print("Arguments:")
        print("  <questionnaire_json>  Path to questionnaire JSON file (required)")
        print("  [output_dir]          Directory for output test plan file (optional)")
        print("                        Default: same directory as input JSON")
        print()
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else os.path.dirname(json_file)
    
    if not os.path.exists(json_file):
        print(f"Error: JSON file not found: {json_file}")
        sys.exit(1)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print("=" * 80)
    print("V4 Test Plan Generator - Complete Pipeline")
    print("=" * 80)
    print()
    
    # Module 1: Build Z3 model
    print("Module 1: Building Z3 model...")
    print("-" * 80)
    model = build_z3_model(json_file)
    print()
    
    # Early check: zero test variables
    if not model['test_variables']:
        print("No test variables found. Cannot generate test plan.")
        sys.exit(0)
    
    # Module 2: Enumerate valid assignments
    print("Module 2: Enumerating valid assignments...")
    print("-" * 80)
    valid_assignments = enumerate_valid_assignments(model)
    print()
    
    if not valid_assignments:
        print("No valid assignments found. Cannot generate test plan.")
        sys.exit(0)
    
    # Determine all reachable questions
    all_reachable = set()
    for assignment in valid_assignments:
        all_reachable.update(assignment['visible_questions'])
    
    # Extract unsatisfiable conditions for unreachable questions
    unsatisfiable_conditions = {}
    never_visible = model.get('never_visible', set())
    questions = model['questions']
    
    for q_num in never_visible:
        q = next((q for q in questions if q['number'] == q_num), None)
        if q and q.get('visibilityCondition'):
            unsatisfiable_conditions[q_num] = q['visibilityCondition']
    
    # Greedy set cover
    print("Greedy Set Cover: Selecting minimal test cases...")
    print("-" * 80)
    test_cases = greedy_set_cover(valid_assignments, all_reachable)
    
    print(f"Selected {len(test_cases)} test cases covering {len(all_reachable)} questions")
    print()
    
    # Module 4: Generate output
    print("Module 4: Generating test plan output...")
    print("-" * 80)
    output_file = generate_test_plan_output(
        test_cases,
        model,
        all_reachable,
        never_visible,
        output_dir,
        unsatisfiable_conditions
    )
    
    print(f"[OK] Test plan saved to: {output_file}")
    print()
    print("=" * 80)
    print("V4 Test Plan Generation Complete")
    print("=" * 80)


if __name__ == '__main__':
    main()
