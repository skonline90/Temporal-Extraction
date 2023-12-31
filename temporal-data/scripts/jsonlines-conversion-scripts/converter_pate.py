#!/usr/bin/env python
# -*- coding:utf-8 -*-
import json
import re
import random
from typing import List
from conversion_utils.preprocessing_utils import find_sublist_in_list
from conversion_utils.preprocessing_file_saver import generate_crossvalidation_folds, save_dataset_splits
from conversion_utils.preprocessing_utils import DatasetNltkTokenizer
import argparse
import sys
import os
import pprint

class PateDatasetConverter:
    """
    This class converts the PATE dataset to the jsonline format. The class takes into account the details of the PATE dataset.
    It also implements crossvalidation and saves the dataset in multiple copies.

    Dataset can be converted in different ways. The following options are available:
        - Single entity class: All timex3 types are mapped to a single entity class e.g. "tempexp"
        - Multiple entity classes: Keeps the original timex3 types e.g. "date", "time", "duration", "set"

    It outputs/splits the dataset into train and test dataset and also outputs a human readable version of the dataset for each split.
    Note: that this can be very memory intensive, if this script is applied to very large datasets.
    """
    def __init__(self, input_filepaths: List[str], output_directory_path: str, single_entity_class: bool, crossvalidation_enabled: bool = False, folds: int = 10) -> None:
        self.input_filepaths = input_filepaths #List of input filepaths
        self.output_directory_path = output_directory_path #Where to save the converted dataset
        self.crossvalidation_enabled = crossvalidation_enabled #Whether to split the dataset into folds or not
        self.folds = folds #If crossvalidation is enabled, how many folds to create
        self.single_entity_class = single_entity_class #Whether to use a single entity class or not

        #Split percentages of the dataset
        self.train_percent = 0.8
        self.test_percent = 0.1
        self.val_percent = 0.1

        #Output file names
        self.output_file_prefix = "pate"
        self.output_file_ending = ".jsonlines"
        self.output_file_train_suffix = "-train" + self.output_file_ending
        self.output_file_test_suffix = "-test" + self.output_file_ending
        self.output_file_val_suffix = "-val" + self.output_file_ending
        self.output_file_full_suffix = "-full" + self.output_file_ending

        #Represents all timex3 types: DATE, TIME, DURATION, SET
        if single_entity_class:
            self.classes_dictionary = {
                "date": "tempexp",
                "time": "tempexp",
                "duration": "tempexp",
                "set": "tempexp"
            }
        else:
            self.classes_dictionary = {
                "date": "date",
                "time": "time",
                "duration": "duration",
                "set": "set"
            }
        
        #Load word tokenizer
        self.word_tokenizer = DatasetNltkTokenizer()
        
        #Load dataset
        self.dataset = self.load_dataset(self.input_filepaths)
        
    def load_dataset(self, dataset_filepaths: List[str]) -> List[dict]:
        """
        Loads the dataset from the specified filepaths.

        Args:
            dataset_filepaths: List of filepath to the dataset files.

        Returns:
            A list of dictionaries. Each dictionary a dataset entry.
        """
        dataset_instances = list()
        for dataset_filepath in dataset_filepaths:
            with open(dataset_filepath, 'r') as file:
                dataset_instances += [json.load(file)]

        dataset = list()
        for dataset_instance in dataset_instances:
            dataset += dataset_instance
        return dataset
    
    def convert_dataset(self) -> None:
        """
        Converts the dataset into json format and writes it to the filesystem.
        The dataset is saved in multiple copies:
            (1) Full dataset
            (2) Train dataset / Test dataset
            (3) Train dataset / Test dataset for each crossvalidation fold

        Prior to conversion the dataset is shuffled.
        """
        json_list = self.create_json_list(self.dataset)
        print(f"Loaded input dataset in memory and created json structure.\n")
        
        random.shuffle(json_list)

        save_dataset_splits(
            json_list=json_list,
            output_directory_path=self.output_directory_path,
            train_percent=self.train_percent,
            test_percent=self.test_percent,
            val_percent=self.val_percent,
            output_file_train_suffix=self.output_file_train_suffix,
            output_file_test_suffix=self.output_file_test_suffix,
            output_file_val_suffix=self.output_file_val_suffix,
            output_file_full_suffix=self.output_file_full_suffix,
            output_file_prefix=self.output_file_prefix,
        )

        if self.crossvalidation_enabled:
            generate_crossvalidation_folds(
                json_list=json_list,
                output_dirname=self.output_directory_path, 
                folds=self.folds,
                output_file_train_suffix=self.output_file_train_suffix,
                output_file_val_suffix=self.output_file_val_suffix,
                output_file_test_suffix=self.output_file_test_suffix,
                output_file_prefix=self.output_file_prefix,
            )

        print("\nConversion complete!")

    def create_json_list(self, original_dataset: List[dict]) -> List[dict]:
        """
        Creates a list of jsons from the dataset. The json files have the desired format.

        Args:
            original_dataset: The dataset in the original format.
        """
        json_list = list()
        for dataset_entry in original_dataset:
            text = dataset_entry["text"].strip()
            tokens = self.word_tokenizer.tokenize(text)

            entities = dataset_entry["entities"]
            timex3_expressions = self.extract_entities(entities, text, tokens)

            json_dictionary = {
                "text": text,
                "tokens": tokens,
                "entity": timex3_expressions
            }
            json_list += [json_dictionary]
        return json_list
    
    def extract_entities(self, entities, original_text, original_text_tokens) -> List[dict]:
        """
        Extracts the timex3 entities from the dataset entry.

        Args:
            entities: The entities of the dataset entry.
            original_text: The original text of the dataset entry.
            original_text_tokens: The tokenized original text of the dataset entry.

        Returns:
            A list of dictionaries. Each dictionary represents a timex3 entity.
        """
        extracted_entities = list()
        for entity in entities:
            timex_entities = entity["TIMEX3"]
            for timex3 in timex_entities:
                if timex3["expression"] == "" and timex3["beginPoint"] == "" and timex3["endPoint"] == "":
                    continue
                timex3_type = timex3["type"].strip().lower()
                timex3_type = self.classes_dictionary[timex3_type]
                duration_text = ""
                if timex3["type"] == "DURATION" and timex3["expression"].strip() == "":
                    duration_regex = self.pate_dataset_duration_span_regex_extractor(timex3["beginPoint"], timex3["endPoint"], entities)
                    pattern_matches = re.findall(duration_regex, original_text)
                    duration_text = pattern_matches[0] if len(pattern_matches) > 0 else ""
                    duration_text = duration_text.strip()
                    if duration_text == "": raise Exception("Duration text is empty.")
                
                text = timex3["expression"].strip() if duration_text == "" else duration_text
                tokens = self.word_tokenizer.tokenize(text)
                entity_start_index, entity_end_index = find_sublist_in_list(original_text_tokens, tokens)
                extracted_entities += [{
                    "text": text,
                    "type": timex3_type,
                    "start": entity_start_index,
                    "end": entity_end_index
                }]
        return extracted_entities

    def pate_dataset_duration_span_regex_extractor(self, beginPoint: str, endPoint: str, entities: List[dict]) -> str:
        """
        Extracts the span regex for a duration timex3 tag. The regex is used to find the duration timex3 tag in the sentence.

        Args:
            beginPoint: The begin point of the duration timex3 tag.
            endPoint: The end point of the duration timex3 tag.
            entities: The entities of the dataset entry.

        Returns:
            A string containing the span regex for the duration timex3 tag.
        """
        span_regex = ".*"
        begin_regex = ""
        end_regex = ""

        beginFound = False
        endFound = False
        for entity in entities:
            timex_entities = entity["TIMEX3"]
            for timex3 in timex_entities:
                if timex3["beginPoint"] == beginPoint:
                    for entity_compare in entities:
                        for timex3_compare in entity_compare["TIMEX3"]:
                            if timex3_compare["tid"] == beginPoint:
                                begin_regex = timex3_compare["expression"]
                                beginFound = True
                if timex3["endPoint"] == endPoint:
                    for entity_compare in entities:
                        for timex3_compare in entity_compare["TIMEX3"]:
                            if timex3_compare["tid"] == endPoint:
                                end_regex = timex3_compare["expression"]
                                endFound = True
        return (begin_regex + span_regex + end_regex) if beginFound and endFound else "NO DURATION FOUND"



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_filepaths",
        "-i", 
        nargs='+', 
        default=["../../original_datasets/pate_and_snips/pate.json"],
        help = "The original Pate dataset may consist of multiple input files. Each of the filepaths needs to be passed."
    )

    parser.add_argument(
        "--output_directory",
        "-o",
        type = str,
        default = "../../entity/my_datasets/jsonlines/fullpate_multi",
        help = "The directory for the newly converted dataset files."
    )

    parser.add_argument(
        "--single_class",
        "-s",
        action = "store_true",
        help = "Wether to have the four timex3 temporal classes or only a single generic one."
    )

    parser.add_argument(
        "--crossvalidation",
        "-c",
        action = "store_true",
        help = "Wether to generate crossvalidation folds or not."
    )

    parser.add_argument(
        "--folds",
        "-f",
        type = int,
        default = 10,
        help = "Number of crossvalidation folds."
    )
    args = parser.parse_args()


    #Validate input
    is_error: bool = False
    if args.input_filepaths is None or args.input_filepaths == []:
        is_error = True

    if not isinstance(args.input_filepaths, list):
        is_error = True

    if args.output_directory is None:
        is_error = True

    if is_error:
        print("Problem with input arguments.")
        sys.exit()

    
    print(f"Loading Pate conversion script...")
    print(f"Following arguments were passed:")
    pprint.pprint(f"Pate dataset input filepaths:    {args.input_filepaths} => {type(args.input_filepaths)}")

    print(f"Output directory:               {args.output_directory} => {type(args.output_directory)}")
    print(f"Single class only:              {args.single_class} => {type(args.single_class)}")
    print(f"Crossvalidation enabled:        {args.crossvalidation} => {type(args.crossvalidation)}")
    print(f"Number of folds:                {args.folds} => {type(args.folds)}")


    print()
    if not os.path.exists(args.output_directory):
        print(f"Output directory does not exist. Creating directory '{os.path.abspath(args.output_directory)}'.\n")
        os.makedirs(os.path.abspath(args.output_directory))

    converter = PateDatasetConverter(
        input_filepaths=args.input_filepaths,
        output_directory_path=args.output_directory,
        single_entity_class=args.single_class,
        crossvalidation_enabled=args.crossvalidation,
        folds=args.folds
    )
    converter.convert_dataset()