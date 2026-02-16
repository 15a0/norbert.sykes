#!/usr/bin/env python3
"""
Questionnaire Utilities

Shared logic for classifying questions, identifying dependencies, and analyzing questionnaire structure.
Used by both questionnaire_dependency_analyzer.py and test_plan_generator.py.
"""

from collections import defaultdict


def extract_options(question_item):
    """Extract options from a question (RadioButtons, Dropdown, Checkbox, etc.)"""
    options = []
    
    if 'options' in question_item:
        for opt in question_item['options']:
            data_value = opt.get('dataValue', '')
            display_value = opt.get('displayValue', '')
            options.append({
                'dataValue': data_value,
                'displayValue': display_value
            })
    
    return options


def extract_referenced_questions(visibility_condition):
    """
    Extract all question references from a visibility condition.
    Returns list of dicts with question_label, operator, and expected_value.
    """
    references = []
    
    if not visibility_condition:
        return references
    
    def traverse_expression(expr):
        if not expr:
            return
        
        operator = expr.get('operator')
        
        # Handle AND/OR (recursive)
        if operator in ['AND', 'OR']:
            traverse_expression(expr.get('left'))
            traverse_expression(expr.get('right'))
        
        # Handle comparison operators
        elif operator in ['EQUALS', 'NOT_EQUALS', 'CONTAINS', 'NOT_CONTAINS', 'INCLUDES']:
            left = expr.get('left', {})
            right = expr.get('right', {})
            
            question_label = left.get('label')
            right_value = right.get('value')
            
            if question_label:
                references.append({
                    'question_label': question_label,
                    'operator': operator,
                    'expected_value': right_value
                })
    
    if 'expression' in visibility_condition:
        traverse_expression(visibility_condition['expression'])
    
    return references


def extract_all_questions(questionnaire):
    """Extract all questions from questionnaire with their attributes."""
    questions = []
    question_number = 1
    
    if 'pages' in questionnaire:
        for page in questionnaire['pages']:
            if 'pageItems' in page:
                for item in page['pageItems']:
                    options = extract_options(item)
                    vis_cond_refs = extract_referenced_questions(item.get('visibilityCondition'))
                    
                    question = {
                        'number': question_number,
                        'label': item.get('label', 'Unknown'),
                        'type': item.get('type', 'Unknown'),
                        'hidden': item.get('hidden', False),
                        'required': item.get('required', False),
                        'options': options,
                        'visibilityCondition': item.get('visibilityCondition'),
                        'visibilityConditionRefs': vis_cond_refs,
                        'defaultAnswer': item.get('defaultAnswer'),
                    }
                    questions.append(question)
                    question_number += 1
    
    return questions


def identify_visible_on_open(questions):
    """
    Identify questions visible on form open.
    Pattern: hidden=false AND visibilityCondition=null
    Returns set of question numbers.
    """
    visible_on_open = set()
    for q in questions:
        if not q['hidden'] and q['visibilityCondition'] is None:
            visible_on_open.add(q['number'])
    return visible_on_open


def build_reverse_dependency_map(questions):
    """
    Build reverse dependency map: which questions reference each question's answer.
    Returns: {question_label: [{'child_number': X, 'child_label': Y, 'operator': Z, 'expected_value': V}]}
    """
    reverse_dependencies = defaultdict(list)
    
    for q in questions:
        for ref in q['visibilityConditionRefs']:
            parent_label = ref['question_label']
            reverse_dependencies[parent_label].append({
                'child_number': q['number'],
                'child_label': q['label'],
                'operator': ref['operator'],
                'expected_value': ref['expected_value']
            })
    
    return reverse_dependencies


def classify_questions(questions, reverse_dependencies):
    """
    Classify questions into TEST_VAR, DATA_COL, and HIDDEN.
    
    TEST_VAR: visible + referenced in other questions' visibility conditions
    DATA_COL: visible + never referenced (no downstream dependencies)
    HIDDEN: hidden=true (backend/system fields)
    
    Returns: {
        'test_variables': set of question numbers,
        'data_collection': set of question numbers,
        'hidden': set of question numbers
    }
    """
    test_variables = set()
    data_collection = set()
    hidden = set()
    
    for q in questions:
        if q['hidden']:
            hidden.add(q['number'])
        elif q['label'] in reverse_dependencies:
            # This question's answer is referenced by other questions
            test_variables.add(q['number'])
        else:
            # This question's answer is not referenced by any other question
            data_collection.add(q['number'])
    
    return {
        'test_variables': test_variables,
        'data_collection': data_collection,
        'hidden': hidden
    }


def get_data_collection_questions(questions, classification):
    """
    Get detailed info about data collection questions.
    Returns list of data collection questions with their attributes.
    """
    data_col_numbers = classification['data_collection']
    return [q for q in questions if q['number'] in data_col_numbers]


def get_test_variables(questions, classification):
    """
    Get detailed info about test variables.
    Returns list of test variable questions with their attributes.
    """
    test_var_numbers = classification['test_variables']
    return [q for q in questions if q['number'] in test_var_numbers]
