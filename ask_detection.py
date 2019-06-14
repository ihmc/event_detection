from allennlp.predictors.predictor import Predictor
predictor = Predictor.from_path("https://s3-us-west-2.amazonaws.com/allennlp/models/srl-model-2018.05.25.tar.gz")

import json
import nltk
import csv
import os
import re
import subprocess

# This library allows python to make requests out.
# NOTE: There is a difference between this and the built in request variable  
# that FLASK provides do  not confuse the two.
import requests

nltk.download('wordnet')
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet as wn
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')

from ask_mappings import sashank_categories_sensitive, sashanks_ask_types, tomeks_ask_types
from catvar_v_alternates import v_alternates


modality_lookup = {}
sentence_modalities = []
word_specific_rules = []


# Url for server hosting coreNLP
coreNLP_server = 'http://panacea:nlp_preprocessing@simon.arcc.albany.edu:44444'

tsurgeon_class = 'edu.stanford.nlp.trees.tregex.tsurgeon.Tsurgeon'

project_path = os.path.abspath(os.path.dirname(__file__))

# Path for files needed for catvar processing
catvar_file = '/catvar.txt'
lcs_file = '/LCS-Bare-Verb-Classes-Final.txt'

# Url for server hosting coreNLP
coreNLP_server = 'http://panacea:nlp_preprocessing@simon.arcc.albany.edu:44444'

# When reading in files locally these directorys must be inside the project directory(i.e. mood and modality)
# They can be named whatever you would like just make sure they exists
# All files meant to be read in should be in the text directory.
# The output directory will be filled with the modality results of processing the input files
input_directory = '/text/'
output_directory = '/output/'
rule_directory = '/generalized-templates_v1_will_change_after_working_on_idiosyncraticRules/'

# Rule directories
# TODO This list will be thinned out as rule sets are chosen for superiority
generalized_rule_directory = '/generalized-templates_v1_will_change_after_working_on_idiosyncraticRules/'
generalized_rule_v2_directory = '/generalized-templates_v2/'
generalized_v3_directory = '/generalized-templates_v3/'
lexical_item_rule_directory = '/lexical-item-rules/'
preprocess_rule_directory = '/idiosyncratic/'

# Paths for the tsurgeon java tool
tregex_directory = '/stanford-tregex-2018-10-16/'
tsurgeon_script = tregex_directory + 'tsurgeon.sh'

lcs_dict = {}
with open('.' + lcs_file) as lcs:
	backup_regex = '\(\s\s:NUMBER \"(.+)\"\s\s:NAME \"(.+)\"\s\s:WORD \((.*)\) \)'
	unit_regex = ':NUMBER \"(.+)\"\s*:NAME \"(.+)\"\s*:WORDS \((.*)\)' 
	lines = lcs.readlines() 
	file_as_string = ''
	for line in lines:
		file_as_string += line

	matches = re.findall(unit_regex, file_as_string, re.MULTILINE)
	#print(matches)
	for match in matches:
		lcs_key = match[0] + ' ' + match[1]
		word_list = match[2].split()
		lcs_dict[lcs_key] = word_list	

#print(lcs_dict)
print('LCS dictionary created')

test_list = []
# catvar_alternates_dict is a dictionary where each key has an array of verbal words from the catvar file
# that exist on a line with more than 1 verbal form. This is to cover cases when a small spelling change is present
# in catvar or when other verbal words exist but were are not a part of the catvar_dict here
catvar_alternates_dict = v_alternates
catvar_dict = {}
with open('.' + catvar_file) as catvar:
	for entry in catvar:
		'''
		v_entries = []
		#if '_V' not in entry_pieces[0]:
		entry_pieces = entry.split('#')
		count = 0
		for index, entry_piece in enumerate(entry_pieces):
			beg_test_word = entry_pieces[0].split('_')[0]
			test_word = entry_piece.split('_')[0]
			if '_V' in entry_piece: #and beg_test_word != test_word:
				v_word = entry_piece.split('_')[0]
				count += 1
				v_entries.append(v_word)
		if count > 1:#and len(v_entries) < 2:
			for word in v_entries:
				alternates_dict[word] = v_entries
		'''
		if '_V' in entry:
			entry_pieces = entry.split('#')

			for entry_piece in entry_pieces:
				if '_V' in entry_piece:
					value_piece_no_POS = entry_piece.split('_')[0]

			for entry_piece in entry_pieces:
				key_piece_no_POS = entry_piece.split('_')[0]	
				catvar_dict[key_piece_no_POS] = {'catvar_value': value_piece_no_POS}

			'''
			if len(entry_pieces) > 1:
				# Must create a key for each piece and it's value the first piece
				for entry_piece in entry_pieces:
					key_piece_no_POS = entry_piece.split('_')[0]
					value_piece_no_POS = entry_pieces[0].split('_')[0]
				catvar_dict[key_piece_no_POS] = {'catvar_value': value_piece_no_POS}
			else:
				# If the entry only has one piece then the key and value are the same 
				piece_no_POS = entry_pieces[0].split('_')[0]
				catvar_dict[piece_no_POS] = {'catvar_value': piece_no_POS}
			'''
		
#print(catvar_dict, 'catvar dicctionary')
print('catvar dictionary create')

preprocess_rules_in_order = []
with open('.' + preprocess_rule_directory + 'ORDER.txt', 'r') as rule_order:
	for rule in rule_order:
		rule = rule.strip('\n')
		preprocess_rules_in_order.append(rule)

print('Preprocess rules loaded')

# Reading a provided CSV as a lexicon and parsing out each word and it's modality
# as well as a list of rules that should apply for each lexical item
# A sequence of 2 or 3 words can exist as well so those are checked for first
lexical_items = []
with open('./ModalityLexiconSubcatTags.csv') as modalityCSV:
	csv_reader = csv.reader(modalityCSV)
	for word, pos, modality, rules in csv_reader:
		lexical_items.append(word)
		for rule in rules.split("|"):
			if rule:
				word_specific_rules.append((word, rule.strip(' '), modality))
		for pos in pos.split("|"):
			modality_lookup[(word, pos)] = modality

print("Lexicon loaded")

if not os.path.exists('.' + lexical_item_rule_directory):
	print('Lexical item rule directory does not exist, creating now');
	os.mkdir('.' + lexical_item_rule_directory)


# Rule here refers to a tuple containing the rule as well as its corresponding lexical item, and modality (lexical item, rule name, modality)
lexical_specific_rules = []
for rule in word_specific_rules:
	if rule[1] + '.txt' not in preprocess_rules_in_order:
		with open('.' + generalized_v3_directory + rule[1] + '.txt') as rule_file:
			filled_in_rule = rule_file.read().replace('**', rule[0])
			rule_name = rule[0] + '-' + rule[2] + '-' + rule[1]

			filled_in_rule = filled_in_rule.replace('TargLabel', 'Targ' + rule[2])
			filled_in_rule = filled_in_rule.replace('TrigLabel', 'Trig' + rule[2])

		# A new file name is built from the combination of the lexical item and the rule
		lexical_specific_rule_file = '.' + lexical_item_rule_directory + rule_name + '.txt'
		#print(lexical_specific_rule_file)
		rule_dict = {}
		rule_dict['rule'] = filled_in_rule
		rule_dict['rule_name'] = rule_name
		rule_dict['modality'] = rule[2]
		rule_dict['lexical_item'] = rule[0]
		lexical_specific_rules.append(rule_dict)
		with open(lexical_specific_rule_file, 'w+') as lexical_rule:
			lexical_rule.write(filled_in_rule)
			
#print(lexical_specific_rules)

def getModality(text):

	# Split input text into sentences
	sentences = nltk.sent_tokenize(text)
	sentence_modalities = []

	for sentence in sentences:
		constituency_parse = parseModality(sentence)
		
		sentence_modalities.append({"sentence": sentence, "matches": constituency_parse})


	return sentence_modalities

def getSrl(text):

	# Split input text into sentences
	sentences = nltk.sent_tokenize(text)
	sentence_srls = []

	for sentence in sentences:
		constituency_parse = parseSrl(sentence)
		sentence_srls.append({"sentence": sentence, "matches": constituency_parse})


	return sentence_srls

def readLocalFiles():
	path = os.path.abspath(os.path.dirname(__file__))
	input_path  = path + input_directory
	output_path = path + output_directory

	for filename in os.listdir(input_path):
		with open(input_path + filename, 'r') as input_file:
			text = input_file.read()
			with open(output_path + 'ouput' + filename + '.json', 'w') as output_file:
				json_modality = getModality(text)
				output_file.write(json.dumps(json_modality, indent=4, sort_keys=False))

	return 

def morphRoot(word):
	wlem = WordNetLemmatizer()
	return wlem.lemmatize(word.lower(),wn.VERB)

def extractTriggerWordAndPos(trigger_string):
	trigger_string = trigger_string.replace('\\n', '');
	match = re.search('\(([A-Z]*) *([a-z]+?)\)', trigger_string)
	trigger_pos = match.group(1)
	trigger_word = match.group(2)
	
	return (trigger_word, trigger_pos)
	
def getTriggerModality(word_and_pos):
	trigger_tuple = (morphRoot(word_and_pos[0].lower()), word_and_pos[1])
	
	if trigger_tuple in modality_lookup:
		return modality_lookup[trigger_tuple]
  
def preprocessSentence(tree):
	with open('./tree.txt', 'w+') as tree_file:
		tree_file.write(tree)
		for rule in preprocess_rules_in_order:
			# Have to return to the beginning of the file so that the new tree overwrites the previous one.
			tree_file.seek(0)

			# This command is taken out of the tsurgeon.sh file in the coreNLP tregex tool.
			# The cp option is added so the class will run without being in the same directory 
			result = subprocess.run(['java', '-mx100m', '-cp', project_path + tregex_directory + 'stanford-tregex.jar:$CLASSPATH', tsurgeon_class, '-treeFile', 'tree.txt', '.' + preprocess_rule_directory + rule], stdout = subprocess.PIPE, text=True)

			tree_file.write(result.stdout)

	return result.stdout


# This function runs regex on a parse tree in order to extract potential trigger and target
# labels that may have been placed on the tree.
def extractTrigsAndTargs(tree):
	trigs_and_targs = []
	
	# Remove new lines so the regex is easier to handle
	tree_no_new_lines = tree.replace('\n', '')
	trig_regex = '(\([A-Z]* *(Trig\w+) *[A-Z]* *([a-z]*)\))'
	targ_regex = '(\([A-Z]* *(Targ\w+) *\(*[A-Z]* *[A-Z]* *([a-z]*)\))'

	# The result of a findall is an array of tuples, where each part of the tuple
	# is a group from the regex, denoted by non escaped parentheses.
	# If a larger group encompasses smaller groups I believe the larger group is first
	# in the tuple
	trig_match = re.findall(trig_regex, tree_no_new_lines)
	targ_match = re.findall(targ_regex, tree_no_new_lines)

	if not trig_match:
		print('Trigger did not match, investigate tree and regex')
		return None
	if not targ_match:
		print('Target did not match, investigate tree and regex')
		return None

	# Extract the trigger and target from the tree, remove "Trig" and "Targ" so the part of speech 
	# can be kept with the word, and extract the modality
	for index, (entire_match, modality, trig) in enumerate(trig_match):
		# TODO keeping this for now as it parses out the trigger and target
		# with their corresponding part of speech
		# May not be needed later on.
		'''
		trig_string = ' '.join(entire_match.split())
		trig_string = re.sub('Trig\w+', '', trig_string)
		targ_string = ' '.join(targ_match[index][0].split())
		targ_string = re.sub('Targ\w+', '', targ_string)
		'''
		modality = modality.replace('Trig', '')
		ask = targ_match[index][2]
		trig_word = trig
		trigs_and_targs.append((trig, targ_match[index][2], modality, ask, trig_word))

	return trigs_and_targs	

def buildParseDict(trigger, target, modality, ask_who, ask, ask_recipient, ask_when, ask_action, confidence, descriptions, s_ask_types, t_ask_types, additional_S_ask_type,  base_word, rule, rule_name):
	parse_dict = {}
	if modality:
		parse_dict['trigger'] = trigger
		parse_dict['target'] = target
		parse_dict['trigger_modality'] = modality
	parse_dict['base_word'] = base_word
	parse_dict['ask_who'] = ask_who
	parse_dict['ask'] = ask
	parse_dict['ask_recipient'] = ask_recipient
	parse_dict['ask_when'] = ask_when
	parse_dict['ask_action'] = ask_action
	parse_dict['confidence'] = confidence
	parse_dict['T_ask_type'] = t_ask_types
	parse_dict['S_ask_type'] = s_ask_types
	parse_dict['additional_S_ask_type'] = additional_S_ask_type
	#parse_dict['semantic_roles'] = descriptions
	
	# Commented for now but useful if debugging which rules are being used
	#parse_dict['rule'] = rule
	#parse_dict['rule_name'] = rule_name
	return parse_dict
	
# Ask types or classes have been provided by Tomek and Sashank, hence s_ask_types and t_ask_types
# This function maps the target word(ask) to a catvar word (the base of a word) which is 
# mapped to LCS (lexical conceptual structures) and eventually those are mapped to the ask types
def getAskTypes(ask):
	verb_types = []
	s_ask_types = []
	t_ask_types = []
	catvar_object = catvar_dict.get(ask)

	if catvar_object != None:
		catvar_word = catvar_object['catvar_value']

		for verb_type, words in lcs_dict.items():
			if catvar_word in words:
				verb_types.append(verb_type)
			else:
				catvar_word_alternates = catvar_alternates_dict.get(ask)
				if catvar_word_alternates:
					for alternate in catvar_word_alternates:
						if alternate in words:
							verb_types.append(verb_type)
							#TODO Ask if this break should be there or if I should get a type for each alternate
							break
				
		
		for vb_type in verb_types:
			for sashank_ask_type, types in sashanks_ask_types.items():
				if vb_type in types and sashank_ask_type not in s_ask_types:
					s_ask_types.append(sashank_ask_type)

			for tomek_ask_type, types in tomeks_ask_types.items():
				if vb_type in types and tomek_ask_type not in t_ask_types:
					t_ask_types.append(tomek_ask_type)
		

	return (s_ask_types, t_ask_types)

# This functions checks to see if the items in a list already exist 
# in the original list and if not then add them.
def appendListNoDuplicates(list_to_append, original_list):
	for item in list_to_append:
		if item not in original_list:
			original_list.append(item)

	return original_list

def getNLPParse(sentence):
	annotators = '/?annotators=tokenize,pos,parse,depparse&tokenize.english=true'
	tregex = '/tregex'
	url = coreNLP_server + annotators

	return requests.post(url, data=sentence.encode(encoding='UTF-8',errors='ignore'))

def getLemmaWords(sentence):
	words = nltk.word_tokenize(sentence)
	return [(morphRoot(word.lower())) for word in words]

def extractAskFromSrl(sentence, base_word, t_ask_types):
	ask_who = ''
	ask = ''
	ask_recipient = ''
	ask_when = ''
	confidence = ''
	selected_verb = ''
	tags_for_verb = ''
	arg0 = []
	arg1 = []
	arg2 = []
	arg_tmp = []
	srl = predictor.predict(sentence=sentence)
	verbs = srl['verbs']
	words = [word.lower() for word in srl['words']]
	descriptions = []

	for verb in verbs:
		if verb['verb'] == base_word:
			selected_verb = verb['verb']
			tags_for_verb = verb['tags']
		descriptions.append(verb['description'])	

	if tags_for_verb:
		for index, tag in enumerate(tags_for_verb):
			tag_label = tag.split('-')[1:2][0] if tag.split('-')[1:2] else ''

			if tag_label == 'ARG0':
				arg0.append(words[index])
			elif tag_label == 'ARG1':
				arg1.append(words[index])
			elif tag_label == 'ARG2':
				arg2.append(words[index])
			elif 'ARGM-TMP' in tag:
				arg_tmp.append(words[index])

	if 'GIVE' in t_ask_types:
		if 'you' in arg2:
			t_ask_types = ["GET"]
		elif 'you' in arg0:
			t_ask_types = ["GIVE"]
		elif 'GET' in t_ask_types:
			if 'you' in arg0:
				t_ask_types = ["GET"]
			if 'i' in arg0 or 'we' in arg0:
				t_ask_types = ["GIVE"]
	elif 'GET' in t_ask_types:
		if 'you' in arg0:
			t_ask_types = ["GET"]
		elif 'i' in arg0 or 'we' in arg0:
			t_ask_types = ["GIVE"]
	elif 'OTHER' in t_ask_types:
		if arg0 and arg1 and arg2:
			if 'you' in arg2:
				t_ask_types = ["GIVE"]
			elif 'you' in arg0:
				t_ask_types = ["GET"]


	if 'GIVE' in t_ask_types:
		if arg0 and arg1 and arg2:
			ask_who = ' '.join(arg0)
			ask = ' '.join(arg1)
			ask_recipient = ' '.join(arg2)
			ask_when = ' '.join(arg_tmp)
			confidence = 'high'
		else:
			ask_who = ' '.join(arg0)
			ask = ' '.join(arg1)
			ask_when = ' '.join(arg_tmp)
			confidence = 'low'
	else:
		if arg0 and arg1 and arg2:
			ask_who = ' '.join(arg2)
			ask = ' '.join(arg1)
			ask_recipient = ' '.join(arg0)
			ask_when = ' '.join(arg_tmp)
			confidence = 'low'
		elif 'GET' in t_ask_types:
			ask = ' '.join(arg1)
			ask_recipient = ' '.join(arg0)
			ask_when = ' '.join(arg_tmp)
			confidence = 'high'
		else:
			ask_who = ' '.join(arg0)
			ask = ' '.join(arg1)
			ask_when = ' '.join(arg_tmp)
			confidence = 'low'
			

	return (ask_who, ask, ask_recipient, ask_when, selected_verb, confidence, descriptions, t_ask_types)	

def parseModality(sentence):
	parse = []
	trigger_string = ''
	target_string = ''
	trigger_modality = ''
	response = getNLPParse(sentence)
	parse_tree = response.json()['sentences'][0]['parse']
	preprocessed_tree = preprocessSentence(parse_tree)

	# Get all words for the sentence and morph them to their root word.
	# Then check each word in the sentence to see if it is in the lexicon and
	# build a list of all the generalized rules that should be tried on the sentence tree
	subsets_per_word = []
	s_ask_types = []
	words = getLemmaWords(sentence)
	for word in words:
		for ask_type, keywords in sashank_categories_sensitive.items():
			if word in keywords and ask_type not in s_ask_types:
				s_ask_types.append(ask_type)	
		if word in lexical_items:
			subset = list(filter(lambda rule: rule['lexical_item'] == word, lexical_specific_rules))
			if subset:
				subsets_per_word.append(subset)

	# If there are not words from the sentence found in the lexicon then we need to check the 
	# preprocessed tree from and triggers
	if len(subsets_per_word) == 0:
		if "Trig" in preprocessed_tree:
			trigs_and_targs = extractTrigsAndTargs(preprocessed_tree)
			if trigs_and_targs == None:
				return None
			for trig_and_targ in trigs_and_targs:
				# TODO store the portions of the tuple in meaningful names
				(trigger, target, modality, ask, trig_word) = trig_and_targ
				(additional_s_ask_types, t_ask_types) = getAskTypes(trig_word)
				parse.append(buildParseDict(trigger, target, modality, '', ask, '', '', '', '',  '',  s_ask_types, t_ask_types, additional_s_ask_types, target, 'preprocessed rules', 'preprocess rules'))

			return parse
	# Here we loop through each set of generalized rules that were gathered above and 
	# try all of them for each word of the sentence that was found in the lexicon until 
	# one of the generalized rules produces a match via tsurgeon	
	for rule_subset in subsets_per_word:
		for rule in rule_subset:
			# Tsurgeon is a part of the stanford corenlp tool set. It must be rune on a file as it will not 
			# aceept just a string. NOTE There may be a way to do just a string that I have not discovered yet.
			# Tsurgeon will edit the parse tree and add trigger and target labels according to the rules that match.
			result = subprocess.run(['java', '-mx100m', '-cp', project_path + tregex_directory + 'stanford-tregex.jar:$CLASSPATH', tsurgeon_class, '-treeFile', 'tree.txt', '.' + lexical_item_rule_directory + rule['rule_name'] + '.txt'], stdout = subprocess.PIPE, text=True)

			# TODO make this more accurate. Currently it is unlikely but still possible that a preprocess rule
			# could have added a Trig with the same modality as a generalized rule. And if the generalized rule 
			# does not match then the Trig from the preprocessed will fire the extracting of triggers when it 
			# should attempt more generalized rules
			if 'Trig' + rule['modality'] in result.stdout:
				trigs_and_targs = extractTrigsAndTargs(result.stdout)
				if trigs_and_targs == None:
					return None
				for trig_and_targ in trigs_and_targs: 
					(trigger, target, modality, ask, trig_word) = trig_and_targ
					(additional_s_ask_types, t_ask_types) = getAskTypes(trig_word)
					parse.append(buildParseDict(trigger, target, modality, '', ask, '', '', '', '', '', s_ask_types, t_ask_types, additional_s_ask_types, target, rule['rule'], rule['rule_name']))

				return parse

def parseSrl(sentence):
	parse = []
	base_word = ''
	conj_base_word = ''
	ask_who = ''
	ask = ''
	ask_recipient = ''
	ask_when = ''
	additional_s_ask_types = []
	s_ask_types = []
	t_ask_types = []
	conj_t_ask_types = []
	conj_additional_s_ask_types = []
	words = getLemmaWords(sentence)
	response = getNLPParse(sentence)
	dependencies = response.json()['sentences'][0]['basicDependencies']
	#print(response.json())
	tokens = response.json()['sentences'][0]['tokens']

	for word in words:
		for ask_type, keywords in sashank_categories_sensitive.items():
			if word in keywords and ask_type not in s_ask_types:
				s_ask_types.append(ask_type)
	
	for dependency in dependencies:
		if dependency['dep'] == 'ROOT':
			base_word = dependency['dependentGloss']
		if dependency['dep'] == 'conj':
			if dependency['governorGloss'] == dependencies[0]['dependentGloss']:
				conj_base_word = dependency['dependentGloss']

	base_word = base_word.lower()
	lem_base_word = morphRoot(base_word)
	(additional_s_ask_types, t_ask_types) = getAskTypes(base_word)
	(additional_lem_s_ask_types, lem_t_ask_types) = getAskTypes(lem_base_word)

	addtional_s_ask_types = appendListNoDuplicates(additional_lem_s_ask_types, additional_s_ask_types)
	t_ask_types = appendListNoDuplicates(lem_t_ask_types, t_ask_types)

	if not t_ask_types:
		t_ask_types.append('OTHER')

	(ask_who, ask, ask_recipient, ask_when, ask_action, confidence, descriptions, t_ask_types) = extractAskFromSrl(sentence, base_word, t_ask_types)

	parse.append(buildParseDict('', '', '', ask_who, ask, ask_recipient, ask_when, ask_action, confidence, descriptions, s_ask_types, t_ask_types, additional_s_ask_types, base_word, '', ''))

	if conj_base_word:
		
		conj_base_word = conj_base_word.lower()
		conj_lem_base_word = morphRoot(conj_base_word)
		(conj_additional_s_ask_types, conj_t_ask_types) = getAskTypes(conj_base_word)
		(conj_additional_lem_s_ask_types, conj_lem_t_ask_types) = getAskTypes(conj_lem_base_word)

		conj_additional_s_ask_types = appendListNoDuplicates(conj_additional_lem_s_ask_types, conj_additional_s_ask_types)
		conj_t_ask_types = appendListNoDuplicates(conj_lem_t_ask_types, conj_t_ask_types)

		if not conj_t_ask_types:
			conj_t_ask_types.append('OTHER')

		(ask_who, ask, ask_recipient, ask_when, ask_action, confidence, descriptions, t_ask_types) = extractAskFromSrl(sentence, conj_base_word, conj_t_ask_types)

		parse.append(buildParseDict('', '', '', ask_who, ask, ask_recipient, ask_when, ask_action, confidence, descriptions, s_ask_types, conj_t_ask_types, conj_additional_s_ask_types, conj_base_word, '', ''))	

	return parse

