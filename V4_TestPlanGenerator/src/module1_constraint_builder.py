#!/usr/bin/env python3
"""
Module 1: Constraint Builder

Translates questionnaire JSON visibility conditions into Z3 constraints.
This module is stable and extracted directly from V3.

Functions:
    build_z3_model(questionnaire_json_path) - Main entry point
    translate_visibility_to_z3(...)         - Translates visibility conditions
    translate_expression(...)               - Recursive expression translator
"""

import json
import os
from z3 import *

from questionnaire_utils import (
    extract_all_questions,
    identify_visible_on_open,
    build_reverse_dependency_map,
    classify_questions,
    get_test_variables,
    get_data_collection_questions
)


# =============================================================================
# MODULE 1: CONSTRAINT BUILDER
# =============================================================================

def build_z3_model(questionnaire_json_path):
    """
    Module 1: Build Z3 variables and constraints from questionnaire JSON.
    
    This function:
    1. Loads the questionnaire JSON
    2. Extracts all questions using V2 utilities
    3. Identifies test variables and their options
    4. Creates Z3 variables for each test variable
    5. Creates Z3 boolean variables for question visibility
    6. Translates visibility conditions into Z3 constraints
    
    Returns dict with:
        - z3_test_vars: {q_num: Z3 Int variable}
        - z3_visible: {q_num: Z3 Bool variable}
        - constraints: list of Z3 constraints
        - questions: list of question dicts
        - test_variables: set of test variable question numbers
        - value_map: {q_num: {string_value: int_encoding}}
    """
    
    # Step 1: Load JSON and extract questions
    with open(questionnaire_json_path, 'r', encoding='utf-8') as f:
        questionnaire = json.load(f)
    
    q_name = questionnaire.get('name', 'questionnaire')
    questions = extract_all_questions(questionnaire)
    
    # Step 2: Classify questions
    reverse_deps = build_reverse_dependency_map(questions)
    classification = classify_questions(questions, reverse_deps)
    test_var_nums = classification['test_variables']
    
    print(f"  Questionnaire: {q_name}")
    print(f"  Total questions: {len(questions)}")
    print(f"  Test variables: {len(test_var_nums)}")
    
    # Step 3: Build value maps for test variables
    # Z3 works with integers, so we map string option values to ints
    # We reserve 0 = "not visible / not assigned"
    value_map = {}  # {q_num: {string_value: int_encoding}}
    
    for q in questions:
        if q['number'] in test_var_nums:
            q_map = {'__NONE__': 0}  # 0 means not visible
            for i, opt in enumerate(q['options'], start=1):
                q_map[opt['dataValue']] = i
            value_map[q['number']] = q_map
    
    # Step 4: Create Z3 variables
    z3_test_vars = {}  # {q_num: Z3 Int}
    z3_visible = {}    # {q_num: Z3 Bool}
    
    # Create a Z3 Int variable for each test variable
    for q_num in sorted(test_var_nums):
        q = next(qx for qx in questions if qx['number'] == q_num)
        z3_test_vars[q_num] = Int(f'Q{q_num}')
        print(f"    Z3 Int variable: Q{q_num} ({q['label']})")
        if q_num in value_map:
            for val_str, val_int in value_map[q_num].items():
                print(f"      {val_int} = {val_str}")
    
    # Create a Z3 Bool variable for each visible question's visibility
    for q in questions:
        if not q['hidden']:
            q_num = q['number']
            z3_visible[q_num] = Bool(f'Q{q_num}_visible')
    
    # Step 5: Build constraints
    constraints = []
    
    # Constraint Type A: Test variable domain constraints
    # Each test variable must be either 0 (not visible) or one of its valid option values
    # SKIP test variables with no static options (Lookup/Dropdown with dynamic sources)
    for q_num in sorted(test_var_nums):
        if q_num in value_map:
            valid_values = list(value_map[q_num].values())  # [0, 1, 2, ...]
            if len(valid_values) <= 1:
                # Only has __NONE__ (0) - no static options (Lookup/Dropdown)
                print(f"    Constraint A (SKIPPED): Q{q_num} has no static options (dynamic source)")
                continue
            constraints.append(Or([z3_test_vars[q_num] == v for v in valid_values]))
            print(f"    Constraint A (domain): Q{q_num} in {valid_values}")
    
    # Constraint Type B: Always-visible questions
    # Questions with no visibility condition are always visible
    for q in questions:
        if not q['hidden'] and q['visibilityCondition'] is None:
            if q['number'] in z3_visible:
                constraints.append(z3_visible[q['number']] == True)
                print(f"    Constraint B (always visible): Q{q['number']} ({q['label']})")
    
    # Constraint Type C: Conditional visibility
    # Translate each visibility condition to a Z3 constraint
    # "Q8 is visible IF Q7 INCLUDES Yes"
    # becomes: z3_visible[8] == (z3_test_vars[7] == value_map[7]['Yes'])
    never_visible_questions = set()  # Track questions with visibility = False
    
    for q in questions:
        if not q['hidden'] and q['visibilityCondition'] is not None:
            if q['number'] in z3_visible:
                z3_condition = translate_visibility_to_z3(
                    q['visibilityCondition'],
                    questions,
                    z3_test_vars,
                    z3_visible,
                    value_map,
                    test_var_nums
                )
                if z3_condition is not None:
                    constraints.append(z3_visible[q['number']] == z3_condition)
                    print(f"    Constraint C (conditional): Q{q['number']} visible IF {z3_condition}")
                    
                    # Check if condition is BoolVal(False) - question can never be visible
                    if is_false(z3_condition):
                        never_visible_questions.add(q['number'])
                else:
                    # Could not translate - assume always visible
                    constraints.append(z3_visible[q['number']] == True)
                    print(f"    Constraint C (fallback): Q{q['number']} - could not translate, assuming visible")
    
    # Constraint Type D: Test variable visibility linkage
    # If a test variable is not visible, its value must be 0 (NONE)
    # If a test variable IS visible, its value must NOT be 0
    # SKIP test variables with no static options (they're always visible with unknown value)
    for q_num in sorted(test_var_nums):
        if q_num in z3_visible and q_num in z3_test_vars:
            if q_num in value_map and len(value_map[q_num]) <= 1:
                # No static options - skip linkage constraint
                print(f"    Constraint D (SKIPPED): Q{q_num} has no static options")
                continue
            constraints.append(
                Implies(Not(z3_visible[q_num]), z3_test_vars[q_num] == 0)
            )
            constraints.append(
                Implies(z3_visible[q_num], z3_test_vars[q_num] != 0)
            )
            print(f"    Constraint D (linkage): Q{q_num} not visible -> value=0, visible -> value!=0")
    
    print(f"\n  Total constraints: {len(constraints)}")
    
    if never_visible_questions:
        print(f"  Detected {len(never_visible_questions)} never-visible questions: {sorted(never_visible_questions)}")
    
    return {
        'z3_test_vars': z3_test_vars,
        'z3_visible': z3_visible,
        'constraints': constraints,
        'questions': questions,
        'test_variables': test_var_nums,
        'value_map': value_map,
        'questionnaire_name': q_name,
        'classification': classification,
        'never_visible': never_visible_questions
    }


def translate_visibility_to_z3(visibility_condition, questions, z3_test_vars, z3_visible, value_map, test_var_nums):
    """
    Translate a JSON visibility condition into a Z3 boolean expression.
    
    Handles operators: EQUALS, NOT_EQUALS, INCLUDES, CONTAINS, AND, OR
    
    Returns a Z3 BoolRef or None if translation fails.
    """
    if not visibility_condition or 'expression' not in visibility_condition:
        return None
    
    return translate_expression(
        visibility_condition['expression'],
        questions,
        z3_test_vars,
        z3_visible,
        value_map,
        test_var_nums
    )


def translate_expression(expr, questions, z3_test_vars, z3_visible, value_map, test_var_nums):
    """
    Recursively translate a visibility condition expression to Z3.
    
    Expression types:
    - AND: And(left, right)
    - OR: Or(left, right)
    - EQUALS: z3_var == encoded_value
    - NOT_EQUALS: z3_var != encoded_value
    - INCLUDES/CONTAINS: z3_var == encoded_value (treated same as EQUALS for our purposes)
    """
    if not expr:
        return None
    
    operator = expr.get('operator')
    
    # Handle AND/OR (recursive)
    if operator == 'AND':
        left_z3 = translate_expression(expr.get('left'), questions, z3_test_vars, z3_visible, value_map, test_var_nums)
        right_z3 = translate_expression(expr.get('right'), questions, z3_test_vars, z3_visible, value_map, test_var_nums)
        if left_z3 is not None and right_z3 is not None:
            return And(left_z3, right_z3)
        return left_z3 or right_z3
    
    if operator == 'OR':
        left_z3 = translate_expression(expr.get('left'), questions, z3_test_vars, z3_visible, value_map, test_var_nums)
        right_z3 = translate_expression(expr.get('right'), questions, z3_test_vars, z3_visible, value_map, test_var_nums)
        if left_z3 is not None and right_z3 is not None:
            return Or(left_z3, right_z3)
        return left_z3 or right_z3
    
    # Handle comparison operators
    if operator in ['EQUALS', 'NOT_EQUALS', 'INCLUDES', 'CONTAINS', 'NOT_CONTAINS']:
        left = expr.get('left', {})
        right = expr.get('right', {})
        
        parent_label = left.get('label')
        expected_value = right.get('value')
        
        if not parent_label:
            return None
        
        # Find the parent question by label
        parent_q = None
        for q in questions:
            if q['label'] == parent_label:
                parent_q = q
                break
        
        if parent_q is None:
            print(f"      WARNING: Could not find parent question '{parent_label}'")
            return None
        
        parent_num = parent_q['number']
        
        # If parent is a test variable with Z3 variable, use it
        if parent_num in z3_test_vars and parent_num in value_map:
            
            # Handle NOT_EQUALS None first - means "has any value" (value != 0)
            # This is common for Lookup/Dropdown fields where "not empty" = visible
            if expected_value is None and operator == 'NOT_EQUALS':
                return z3_test_vars[parent_num] != 0
            
            encoded_value = value_map[parent_num].get(expected_value)
            
            if encoded_value is None:
                # Value not in our map - might be a value we haven't seen
                print(f"      WARNING: Value '{expected_value}' not in value map for Q{parent_num}")
                return None
            
            if operator in ['EQUALS', 'INCLUDES', 'CONTAINS']:
                return z3_test_vars[parent_num] == encoded_value
            elif operator == 'NOT_EQUALS':
                return z3_test_vars[parent_num] != encoded_value
            elif operator == 'NOT_CONTAINS':
                return z3_test_vars[parent_num] != encoded_value
        
        # If parent is a hidden question with a constant default value
        if parent_q['hidden'] and parent_q['defaultAnswer'] is not None:
            default = parent_q['defaultAnswer']
            
            # FIX 3: Template variable heuristic
            # If default is a template variable (e.g., ${service.name}), assume it will equal
            # the expected value at runtime. This enables test generation for service-specific forms.
            if isinstance(default, str) and '${' in default:
                # Template variable - assume it equals the expected value for testing
                if operator in ['EQUALS', 'INCLUDES', 'CONTAINS']:
                    # Assume template will be resolved to expected value
                    return BoolVal(True)
                elif operator == 'NOT_EQUALS':
                    # Assume template will be resolved to expected value, so NOT_EQUALS is False
                    return BoolVal(False)
            
            # Constant default value - evaluate directly
            if operator in ['EQUALS', 'INCLUDES', 'CONTAINS']:
                # Condition is always true if default matches expected
                return BoolVal(str(default) == str(expected_value))
            elif operator == 'NOT_EQUALS':
                return BoolVal(str(default) != str(expected_value))
        
        # If parent is not a test variable and not hidden with default
        # It might be a visible question we can't control - assume condition is met
        print(f"      WARNING: Parent Q{parent_num} ({parent_label}) is not a test variable, assuming condition met")
        return BoolVal(True)
    
    print(f"      WARNING: Unknown operator '{operator}'")
    return None
