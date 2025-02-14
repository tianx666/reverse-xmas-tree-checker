#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0+
#
# Copyright (c) 2025, tianx666.
# Copyright (c) 2016, Solarflare Communications Ltd.

import sys
import os
import re

# 'bool' is not really primitive, but it's an omnipresent typedef
# 'float' and 'double' are C primitive types, but should not be used in
# kernel code.
# While C does not permit declaring a variable of type void, derived
# types (such as pointer to void) can be declared.
primitive_types = ['signed', 'unsigned', 'char', 'short', 'int', 'long',
                   'size_t', 'intptr_t', 'uintptr_t', 'void',
                   'bool', 'float', 'double', 'struct', 'union', 'enum']
# Of course this list is non-exhaustive. Fortunately the vast majority
# of kernel types are bare structs rather than typedefs.
kernel_typedefs = ['u8', 'u16', 'u32', 'u64', 's8', 's16', 's32', 's64',
                   'cpumask_var_t']
# I don't think declaring an extern variable inside a function is legal,
# but let's count it as a declaration nonetheless.
storage_classes = ['auto', 'static', 'register', 'extern']
# Similarly, I'm not sure you can declare restricted variables outside of
# a function parameter list, but language lawyering is not this script's
# job, so let's just handle it anyway.
type_qualifiers = ['const', 'volatile', 'restrict']

def is_decl(line):
    """Determine whether a line looks like it's declaring a variable.
    
    A declaration begins with a type name, a storage-class, or a type
    qualifier. No sanely-formatted non-declaration should ever do so.
    """
    decl_openers = (primitive_types + kernel_typedefs + storage_classes +
                    type_qualifiers)
    # Get first word in line
    word, _, _ = line.partition(' ')
    return word in decl_openers

location_re = re.compile(r'-\d+,\d+ \+(\d+),\d+')

def check_file(f):
    last_decl = None
    in_comment = False
    in_struct = False
    in_function = False
    is_diff = False
    viols = []
    li = 0  # line numbering

    for line in f.readlines():
        li += 1
        # Check for diff context lines, they will tell us whether we're in a
        # function or a struct/union/enum definition. They also let us know
        # that this file is a diff, and give us the current line number
        if line.startswith('@@'):
            is_diff = True
            location, _, context = line[2:].partition('@@')
            m = location_re.search(location)
            if m:
                li = int(m.group(1))
            in_struct = False
            in_function = False
            in_comment = False
            if ':' in context or '(' in context:
                in_function = context.strip()
            elif 'struct' in context or 'enum' in context or 'union' in context:
                in_struct = context.strip()
        # If it's a diff, we want lines starting with + or space, but not -,
        # and we want to strip the leading + before parsing further.
        # If it's not a diff, we want all lines, but no line should ever
        # start with -, nor be indented by a single space.
        if line.startswith('-'):
            li -= 1
            continue
        plus = False
        if line.startswith('+') or line.startswith(' '):
            plus = line[0] == '+'
            line = line[1:]
        # Handle comments
        co = line.count('/*')
        cc = line.count('*/')
        if co > cc:
            in_comment = True
        if cc > co:
            in_comment = False
        if in_comment:
            continue
        if line.strip().startswith('/*'):
            # Assume the whole line is a comment
            continue
        # Ignore preprocessor directives
        if line.startswith('#'):
            continue
        # Check for end of block (unindented closing brace)
        if line.startswith('}'):
            in_struct = False
            in_function = False
            in_comment = False
        # If we're not at least a single tab indented, we can't be inside a
        # function or struct, so just look for start-of-block
        if not line.startswith('\t'):
            in_function = False
            in_struct = False
            if line.startswith('{'):
                # Must be a function, as structs etc are supposed to have
                # their { at the end of the line
                in_function = line.strip()
                last_decl = None
            elif '{' in line:
                # Either a struct definition, or a declaration of a static
                # struct variable. Probably.
                in_struct = line.strip()
            continue
        # Remove whitespace, now we're done looking at indentation
        line = line.strip()
        if is_decl(line) and in_function:
            if last_decl is not None and (plus or last_decl[1] or not is_diff):
                if len(line) > len(last_decl[0]):
                    viols.append((last_decl[0], line, li))
            last_decl = (line, plus)
        elif line:
            last_decl = None
    return viols

def report(name, viols):
    if viols:
        print("WARNING: Violation(s) in", name)
        for last, line, li in viols:
            print("Line %d" % (li - 1,))
            print('\t' + last)
            print('\t' + line)
    else:
        print("No problems found in", name)

if len(sys.argv) == 1:
    viols = check_file(sys.stdin)
    report("input", viols)
else:
    for fn in sys.argv[1:]:
        with open(fn, 'r', encoding='utf-8') as f:
            viols = check_file(f)
        name = os.path.basename(fn)
        report(name, viols)
