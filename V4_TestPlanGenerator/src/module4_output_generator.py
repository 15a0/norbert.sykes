#!/usr/bin/env python3
"""
Module 4: Output Generator

Generates formatted test plan output files from test cases and model data.
This module is stable and extracted directly from V3.

Functions:
    generate_test_plan_output(test_cases, model, all_visible_questions, never_visible, output_dir)
"""

import os
import json


# =============================================================================
# MODULE 4: OUTPUT GENERATOR
# =============================================================================

def format_visibility_condition(condition):
    """
    Format a visibility condition for human-readable display.
    
    Args:
        condition: Either a string or dict representing the visibility condition
    
    Returns:
        Formatted string suitable for output
    """
    if isinstance(condition, str):
        return condition
    
    if isinstance(condition, dict):
        # Try to extract readable parts from the condition dict
        if 'expression' in condition:
            expr = condition['expression']
            if isinstance(expr, dict):
                operator = expr.get('operator', 'UNKNOWN')
                left = expr.get('left', {})
                right = expr.get('right', {})
                
                left_label = left.get('label', 'Unknown')
                right_value = right.get('values', [right.get('value', 'Unknown')])
                if isinstance(right_value, list) and right_value:
                    right_value = right_value[0]
                
                # Map operators to readable format
                op_map = {
                    'EQUALS': '==',
                    'NOT_EQUALS': '!=',
                    'CONTAINS': 'contains',
                    'NOT_CONTAINS': 'does not contain'
                }
                op_symbol = op_map.get(operator, operator)
                
                return f"{left_label} {op_symbol} {right_value}"
    
    # Fallback: return JSON representation
    return json.dumps(condition, indent=2)

def generate_test_plan_output(test_cases, model, all_visible_questions, never_visible, output_dir, unsatisfiable_conditions=None):
    """
    Module 4: Generate formatted test plan output file.
    
    Args:
        test_cases: List of test cases with assignments and coverage
        model: The model dict from build_z3_model()
        all_visible_questions: Set of all reachable question numbers
        never_visible: Set of never-visible question numbers
        output_dir: Directory to write output file
        unsatisfiable_conditions: Dict mapping question numbers to their unsatisfiable conditions
    
    Returns:
        Path to generated output file
    """
    
    questionnaire_name = model['questionnaire_name']
    questions = model['questions']
    test_var_nums = model['test_variables']
    value_map = model['value_map']
    
    if unsatisfiable_conditions is None:
        unsatisfiable_conditions = {}
    
    # Create safe filename
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in questionnaire_name)
    output_file = os.path.join(output_dir, f"{safe_name}_test_plan_v4.txt")
    
    # Identify data collection questions (visible but not test variables)
    data_collection = []
    for q in questions:
        if not q['hidden'] and q['number'] not in test_var_nums and q['number'] not in never_visible:
            data_collection.append(q)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 100 + "\n")
        f.write(f"TEST PLAN (V4) - {questionnaire_name}\n")
        f.write("=" * 100 + "\n\n")
        
        # Summary
        f.write("SUMMARY\n")
        f.write("-" * 100 + "\n")
        f.write(f"Test variables: {len(test_var_nums)}\n")
        f.write(f"Total test cases: {len(test_cases)}\n")
        f.write(f"Reachable questions: {len(all_visible_questions)}\n")
        
        if never_visible:
            f.write(f"Unreachable questions (excluded from coverage): {len(never_visible)}\n")
        
        if test_cases:
            f.write(f"Min questions per case: {min(tc['question_count'] for tc in test_cases)}\n")
            f.write(f"Max questions per case: {max(tc['question_count'] for tc in test_cases)}\n")
            f.write(f"Avg questions per case: {sum(tc['question_count'] for tc in test_cases) / len(test_cases):.1f}\n")
            
            # Coverage status
            coverage_pct = (len(all_visible_questions) / len(all_visible_questions)) * 100 if all_visible_questions else 0
            f.write(f"Coverage: {len(all_visible_questions)}/{len(all_visible_questions)} ({coverage_pct:.0f}%)\n")
        else:
            f.write("No test cases generated\n")
        
        f.write("\n")
        
        # Instructions for testers
        f.write("=" * 100 + "\n")
        f.write("INSTRUCTIONS FOR TESTERS\n")
        f.write("=" * 100 + "\n\n")
        f.write("TEST VARIABLES (vary these to cover all paths):\n")
        f.write("  These questions control form flow. Their answers determine which other questions appear.\n")
        f.write("  Follow the assignments in each test case exactly.\n\n")
        f.write("DATA COLLECTION QUESTIONS (enter any valid value):\n")
        f.write("  These questions do NOT affect form flow. Their specific values don't matter for testing.\n")
        f.write("  You can enter:\n")
        f.write("    - Text fields: any text (e.g., 'TEST CASE' or placeholder text)\n")
        f.write("    - Dropdowns/Select: any available option\n")
        f.write("    - Checkboxes: any state (checked/unchecked)\n")
        f.write("    - Date fields: any valid date\n")
        f.write("    - Required fields: must enter something, but any valid value works\n")
        f.write("    - Optional fields: can skip if not required\n\n")
        
        # Test variables
        f.write("=" * 100 + "\n")
        f.write("TEST VARIABLES\n")
        f.write("=" * 100 + "\n\n")
        for q_num in sorted(test_var_nums):
            q = next(qx for qx in questions if qx['number'] == q_num)
            f.write(f"Q{q_num}: {q['label']}\n")
            if q_num in value_map and value_map[q_num]:
                options = [k for k in value_map[q_num].keys() if k != '__NONE__']
                if options:
                    f.write(f"  Options: {', '.join(options)}\n")
        f.write("\n")
        
        # Test cases
        f.write("=" * 100 + "\n")
        f.write("TEST CASES\n")
        f.write("=" * 100 + "\n\n")
        
        for tc in test_cases:
            f.write(f"Test Case {tc['number']}\n")
            f.write("-" * 100 + "\n")
            
            # Identify which test variables are visible in this test case
            visible_test_vars_in_case = [q for q in tc['visible_questions'] if q in test_var_nums]
            
            f.write("TEST VARIABLE ASSIGNMENTS (required - follow exactly):\n")
            
            # Show ALL visible test variables with their values from complete_assignment
            for var_num in sorted(visible_test_vars_in_case):
                q = next(qx for qx in questions if qx['number'] == var_num)
                
                # Get the value from the complete assignment (which includes all test variable values)
                if var_num in tc['complete_assignment']:
                    value = tc['complete_assignment'][var_num]
                else:
                    # Fallback to the minimal assignment if somehow not in complete
                    value = tc['assignment'].get(var_num, "[Not assigned]")
                
                f.write(f"  Q{var_num} ({q['label']}): {value}\n")
            
            f.write(f"\nVisible questions ({tc['question_count']}):\n")
            
            # Separate test variables from data collection in visible questions
            visible_data_col = [q for q in tc['visible_questions'] if q not in test_var_nums]
            
            if visible_data_col:
                f.write(f"  DATA COLLECTION (enter any valid value): {', '.join(f'Q{q}' for q in sorted(visible_data_col))}\n")
            
            f.write("\n")
        
        # Complete question reference
        f.write("=" * 100 + "\n")
        f.write("COMPLETE QUESTION REFERENCE\n")
        f.write("=" * 100 + "\n\n")
        f.write("All questions in this questionnaire (for tester reference):\n\n")
        
        for q in sorted(questions, key=lambda x: x['number']):
            if not q['hidden']:
                q_type = "TEST VAR" if q['number'] in test_var_nums else "DATA COL"
                status = " (UNREACHABLE)" if q['number'] in never_visible else ""
                f.write(f"Q{q['number']}: {q['label']} ({q_type}){status}\n")
        f.write("\n")
        
        # Unreachable questions section (if any)
        if never_visible:
            f.write("=" * 100 + "\n")
            f.write("UNREACHABLE QUESTIONS (Cannot be tested)\n")
            f.write("=" * 100 + "\n\n")
            f.write("These questions have visibility conditions that are always False.\n")
            f.write("They cannot be displayed to users and are excluded from test coverage.\n\n")
            for q_num in sorted(never_visible):
                q = next(qx for qx in questions if qx['number'] == q_num)
                f.write(f"Q{q_num}: {q['label']}\n")
                
                # Show unsatisfiable conditions if available
                if q_num in unsatisfiable_conditions:
                    conditions = unsatisfiable_conditions[q_num]
                    formatted = format_visibility_condition(conditions)
                    f.write(f"  Visibility condition: {formatted}\n")
                
                f.write("\n")
    
    return output_file
