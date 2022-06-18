#!/usr/bin/env python
# -*- coding: UTF-8 -*-
'''
Braille symbols declaration
'''

# constants for special symbols label
num_sign = '##'
caps_sign = 'CC'
markout_sign = 'XX'
sin_nm_sign = 'nm' #sagngnaka sign
halkirima = '|'

# general symbols common for various languages
sym_map = {
    '256': '.',
    '2'  : ',',
    '25' : ':',
    '26' : '?',
    '23' : ';',
    '235': '!',
    '2356':'()', # postprocess to (, ). Labeled as ((, )), ()
    '126':'(',
    '345':')',
    '36' : '-',
    '34' : '/',
    '3456': num_sign,
    '123456': markout_sign,
    '23': sin_nm_sign, #sagngnaka sign
    '4': halkirima, #halkirima sign
}

# Sinahala symbols
alpha_map_SIN = {
    '1'  : 'අ',
    '345' : 'ආ',
    '12356':'ඇ',
    '12456':'ඈ',
    '24' : 'ඉ',
    '35' : 'ඊ',
    '136' : 'උ',
    '1256' : 'ඌ',
    '15' : 'එ',
    '26' : 'ඒ',
    '34' : 'ඓ',
    '1346' : 'ඔ',
    '135' : 'ඕ',
    '246' : 'ඖ',
    '13' : 'ක', 
    '46' : 'ඛ',
    '1245' : 'ග',
    '126' : 'ඝ',
    '346' : 'ඬ',
    '14' : 'ච',
    '16' : 'ඡ',
    '245' : 'ජ',
    '356' : 'ඣ',
    '25' : 'ඤ',
    '23456' : 'ට',
    '2456' : 'ඨ',
    '1246' : 'ඩ',
    '123456' : 'ඪ',
    '1356' : 'ණ',
    '2345' : 'ත',
    '1456' : 'ථ',
    '145' : 'ද',
    '2346' : 'ධ',
    '1345' : 'න',
    '1234' : 'ප',
    '156' : 'ඵ',
    '12' : 'බ',
    '45' : 'භ',
    '134' : 'ම',
    '13456' : 'ය',
    '1235' : 'ර',
    '123' : 'ල',
    '456' : 'ළ',
    '1236' : 'ව',
    '12346' : 'ශ',
    '146' : 'ෂ',
    '234' : 'ස',
    '125' : 'හ',
    '124' : 'ෆ',
    '12345' : 'ඥ',
    '4' : '|',
    '23' : 'nm',

}


# Digit symbols (after num_sign)
num_map = {
    '1': '1',
    '12': '2',
    '14': '3',
    '145': '4',
    '15': '5',
    '124': '6',
    '1245': '7',
    '125': '8',
    '24': '9',
    '245': '0',
}

# Digits in denominators of fraction
num_denominator_map = {
    '2': '/1',
    '23': '/2',
    '25': '/3',
    '256': '/4',
    '26': '/5',
    '235': '/6',
    '2356': '/7',
    '236': '/8',
    '35': '/9',
    '356': '/0', # postprocess num 0 /0 to %
}

# Symbols for Math Braille (in Russian braille, I suppose)
math = {
    '2': ',',  # decimal separator
    '3': '..',  # postprocess to "." (thousand separator) if between digits else to * (multiplication).
    '235': '+',
    '36': '-',
    '236': '*',
    '256': '::',  # postprocess to ":" (division).
    '246': '<',
    '135': '>',
    '2356': '=',
    '126':'(',
    '345':')',
    '12356': '[',
    '23456': ']',
    '246': '{',
    '135': '}',
    '456': "|",
    '6': "en",
    '46': "EN",
}

# Codes for dicts
letter_dicts = {
    'SYM': sym_map,
    'RU': alpha_map_SIN,
    'NUM': num_map,
    'NUM_DENOMINATOR': num_denominator_map,
    'MATH_RU': math,
}

