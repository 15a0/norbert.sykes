#!/usr/bin/env python3
"""
Module 3: Z3 Validator

Validates test variable assignments against Z3 constraints and determines
which questions are visible for each valid assignment.
This module is stable and extracted directly from V3.

Functions:
    validate_assignment(assignment, model) - Validates and returns visible questions
"""

from z3 import *


# =============================================================================
# MODULE 3: Z3 VALIDATOR
# =============================================================================

def validate_assignment(assignment, model):
    """
    Module 3: Validate if a candidate test case assignment is logically possible.
    
    Takes an assignment like: {7: "Yes", 11: "No"} (question numbers to values)
    Returns: (is_valid, visible_questions, complete_assignment, error_message)
    
    Args:
        assignment: dict mapping question numbers to string values
        model: the model dict from build_z3_model()
    
    Returns:
        tuple: (bool, list, dict, str)
            - is_valid: True if assignment is satisfiable
            - visible_questions: list of question numbers that are visible
            - complete_assignment: dict with ALL test variable values (including implied ones)
            - error_message: None if valid, error string if invalid
    """
    
    # Create a new solver instance
    solver = Solver()
    
    # Add all the base constraints
    solver.add(model['constraints'])
    
    # Add the assignment as additional constraints
    for q_num, value_str in assignment.items():
        if q_num not in model['z3_test_vars']:
            return False, [], {}, f"Question Q{q_num} is not a test variable"
        
        if q_num not in model['value_map']:
            return False, [], {}, f"Question Q{q_num} has no value map"
        
        # Encode the string value to int
        encoded_value = model['value_map'][q_num].get(value_str)
        if encoded_value is None:
            return False, [], {}, f"Value '{value_str}' not valid for Q{q_num}"
        
        # Add constraint: this test variable must equal this value
        solver.add(model['z3_test_vars'][q_num] == encoded_value)
    
    # Check if the assignment is satisfiable
    result = solver.check()
    
    if result == sat:
        # Valid assignment - extract which questions are visible and complete test variable values
        m = solver.model()
        visible_questions = []
        complete_assignment = {}
        
        # Get visible questions
        for q_num in sorted(model['z3_visible'].keys()):
            vis = m.evaluate(model['z3_visible'][q_num])
            if is_true(vis):
                visible_questions.append(q_num)
        
        # Get complete test variable assignment (decode from Z3 model)
        # Only process variables that have value_map entries with actual options (not just __NONE__)
        # Variables without real options are dynamic sources (skipped during constraint building)
        for q_num in model['test_variables']:
            if q_num in model['z3_test_vars'] and q_num in model['value_map'] and len(model['value_map'][q_num]) > 1:
                z3_val = m.evaluate(model['z3_test_vars'][q_num])
                int_val = z3_val.as_long()
                
                # Decode the integer value back to string using value_map
                for string_val, encoded_val in model['value_map'][q_num].items():
                    if encoded_val == int_val and string_val != '__NONE__':
                        complete_assignment[q_num] = string_val
                        break
        
        return True, visible_questions, complete_assignment, None
    
    elif result == unsat:
        # Invalid assignment - constraints are contradictory
        return False, [], {}, "Assignment creates contradictory constraints (unsat)"
    
    else:
        # Unknown - solver couldn't determine
        return False, [], {}, f"Solver returned unknown: {result}"
