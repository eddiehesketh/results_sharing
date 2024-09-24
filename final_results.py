import ollama
import csv
import json
import re

print("Script started...")

# Specify the paths and model
input_csv_path = '/Users/lachyshinnick/Downloads/valid_reports.csv'  # Replace with your input CSV file path
output_csv_path = '/Users/lachyshinnick/Desktop/codes/ollamaTest/final_results.csv'  # Replace with your output CSV file path
error_csv_path = '/Users/lachyshinnick/Desktop/codes/ollamaTest/error.csv'  # Replace with your error file path
desiredModel = 'llama3.1:latest'


# Function to extract JSON from model response
def extract_json_from_response(response_text):
    try:
        # Ensure response is cleanly formatted and extract the first JSON object found
        json_matches = re.findall(r'({.*?})', response_text, re.DOTALL)
        if json_matches:
            json_str = json_matches[-1].replace("'", '"')  # Fix apostrophes for valid JSON
            return json.loads(json_str)
        else:
            return {"Error": "Invalid JSON"}
    except (ValueError, json.JSONDecodeError):
        return {"Error": "Invalid JSON"}

# Function to clean findings output
def clean_findings(findings):
    if isinstance(findings, list):
        # Join the list into a single string
        cleaned_findings = "; ".join(findings)
    else:
        # In case it's a string, directly use it
        cleaned_findings = findings

    # Remove unwanted symbols, if any (e.g., square brackets or apostrophes)
    cleaned_findings = re.sub(r"[\[\]']", "", cleaned_findings)
    #remove random fullstops
    cleaned_findings = re.sub(r'\.(?!$)', '', cleaned_findings)

    # Split the findings into individual statements
    statements = cleaned_findings.split('; ')
    updated_statements = []
    for statement in statements:
        # Replace "There are" with "There is" at the beginning of the statement
        updated_statement = re.sub(r'^There are', 'There is', statement)
        
        # Advanced replacements for statements starting with "The "
        if updated_statement.startswith('The '):
            # Try matching "The X is Y"
            match_is = re.match(r'^The (.+?) is (.+)', updated_statement)
            # Try matching "The X are Y"
            match_are = re.match(r'^The (.+?) are (.+)', updated_statement)
            if match_is:
                subject = match_is.group(1)
                predicate = match_is.group(2)
                updated_statement = f'There is {predicate} {subject}'
            elif match_are:
                subject = match_are.group(1)
                predicate = match_are.group(2)
                updated_statement = f'There is {predicate} {subject}'
            else:
                # For other cases starting with "The ", replace "The " with "There is "
                updated_statement = re.sub(r'^The ', 'There is ', updated_statement)
        
        updated_statements.append(updated_statement)

    # Rejoin the statements
    final_findings = '; '.join(updated_statements)

    return final_findings

def extract_findings(report_content, file_name):
    prompt = f"""
        <|begin_of_text|><|start_header_id|>system<|end_header_id|>

        You are a helpful assistant trained to extract key medical findings from radiology reports.

        **Instructions**:

        - **Output Format**: Provide findings in JSON format with the key "Findings". The value should be a string containing one or more statements.
        - **Statement Format**:
        - For **positive findings**:
            - If the location is mentioned: "There is <diagnosis> located at <location>."
            - If the location is not mentioned: "There is <diagnosis>."
        - For **negative findings** (only if explicitly mentioned in the report):
            - "There is no <diagnosis>."
        - For **normal findings**:
            - If explicitly mentioned in the report, include them as: "There is normal <structure>."
            - If the term "unremarkable" is used to describe a body part, interpret this as "There is no abnormality at <body part>."
            - **You are not allowed to use the word "unremarkable" in the output.** Replace it with the statement "There is no abnormality at <body part>."
        - **General Rules**:
        - **Do not hallucinate**: Only include information explicitly mentioned in the report. Do not make any assumptions or create findings that are not directly stated.
        - **One finding per sentence**: Do not combine findings into a single sentence using conjunctions like "and" or "with". Each statement should describe one finding at one location.
        - **If a sentence in the report says "There is <condition-1> and <condition-2> at <location>", split it into two separate findings like: "There is <condition-1> at <location>; There is <condition-2> at <location>".**
        - **Do not use conjunctions like "and" or "with" to connect multiple findings**. Instead, separate each finding into its own sentence.
        - **Use nouns instead of adverbs** to describe locations. For example, replace "subdiaphragmatically" with "at sub-diaphragm".
        - **Remove adjectives describing severity or visibility** unless they are clinically significant. For example, remove words like "mild" or "conspicuous" unless explicitly required for diagnosis.
        - **Include** all findings mentioned in the report, both abnormal and normal.
        - **Do not** include speculative or uncertain findings. Exclude any statements containing words like "possible", "suggests", "may indicate", "could", "probably", etc.
        - **Do not** include redundant or repetitive statements.
        - **Do not** include any references to previous X-rays or imaging results. Focus solely on the current medical findings and diagnosis in the report.
        - **Ensure** that each statement starts with "There is", "There is no", or "There is normal" as per the format.
        - **Only include** findings that strictly adhere to the required format and information given in the report.

        **Examples**:

        **Example 1**:

        Report Content:
        "there is a nasogastric tube located subdiaphragmatically with its tip projected over the T12 vertebra."

        Findings:
        {{
        "Findings": "There is a nasogastric tube located at the sub-diaphragm; There is a tip located at the T12 vertebra."
        }}

        **Example 1 note**: The adjective "subdiaphragmatically" is removed and replaced with the noun "sub-diaphragm" to maintain consistency in terminology. The tip projection is given its own sentence to ensure only one finding per sentence. The conjunction "with" is avoided.

        **Example 2**:

        Report Content:
        "there is a conspicuous gas-filled and dilated bowel loop located at the left mid-abdomen."

        Findings:
        {{
        "Findings": "There is a gas-filled bowel loop located at the left mid-abdomen; There is a dilated bowel loop located at the left mid-abdomen."
        }}

        **Example 2 note**: The adjective "conspicuous" is removed as it is unnecessary. The phrase "gas-filled and dilated bowel loop" is split into two sentences to ensure only one finding per sentence. The word "and" is avoided, and the sentence structure is simplified.

        **Example 3**:

        Report Content:
        "there is central bronchial wall thickening and a mild peribronchial interstitial opacity located at upper lower zones."

        Findings:
        {{
        "Findings": "There is central bronchial wall thickening located at upper lower zones; There is a peribronchial interstitial opacity located at upper lower zones."
        }}

        **Example 3 note**: The adjective "mild" is removed as it does not contribute to the essential finding. The findings are separated into two sentences, with each describing one distinct condition. The conjunction "and" is removed to prevent the combination of findings into one sentence.

        **Example 4**:

        Report Content:
        "the lungs are clear. heart size is normal. no pleural effusion."

        Findings:
        {{
        "Findings": "There is clear lungs; There is normal heart size; There is no pleural effusion."
        }}

        **Example 4 note**: The response succinctly identifies key positive and negative findings about the lungs, heart size, and pleural effusion. The response follows the required format, with each finding presented in a separate sentence.

        **Example 5**:

        Report Content:
        "no orbital floor fracture. no maxillary sinus fluid level. no nasal bone fracture. no evidence of zygomatic arch fracture."

        Findings:
        {{
        "Findings": "There is no orbital floor fracture; There is no maxillary sinus fluid level; There is no nasal bone fracture; There is no zygomatic arch fracture."
        }}

        **Example 5 note**: This output concisely captures multiple negative findings. The use of "There is no" clearly communicates the absence of fractures and fluid levels, maintaining adherence to the required format without unnecessary details.

        **Example 6**:

        Report Content:
        "there is gas and faeces throughout nondistended colon with mild faecal loading of the transverse colon."

        Findings:
        {{
        "Findings": "There is gas located at nondistended colon; There is faeces located at nondistended colon; There is mild faecal loading located at transverse colon."
        }}

        **Example 6 note**: This output effectively breaks down multiple findings from a single sentence into separate statements. Each finding is clearly presented in its own sentence, ensuring clarity and proper adherence to the required format.

        **Explanation**: Each finding is presented in a separate sentence. Adjectives that describe severity or visibility are omitted unless essential. Nouns are used consistently to describe locations, avoiding adverbs like "subdiaphragmatically". The conjunctions "and" and "with" are avoided to ensure each statement covers only one finding.

        <|eot_id|><|start_header_id|>user<|end_header_id|>

        **Report Content**:
        "{report_content}"

        <|eot_id|><|start_header_id|>assistant<|end_header_id|>
    """

    max_retries = 10
    for attempt in range(max_retries):
        try:
            response = ollama.chat(model=desiredModel, messages=[
                {'role': 'user', 'content': prompt},
            ])
            raw_content = response['message']['content'].strip()
            # Extract JSON
            print(raw_content)
            structured_data = extract_json_from_response(raw_content)
            if "Error" not in structured_data:
                # Successfully extracted findings
                return structured_data
            else:
                print(f"Attempt {attempt+1} failed due to invalid JSON in findings for {file_name}")
        except Exception as e:
            print(f"Attempt {attempt+1} failed processing findings for file {file_name}: {e}")
    # After retries, return error
    print(f"Skipping sentence after {max_retries} attempts in file {file_name}")
    structured_data = {"Error": "Failed after retries"}
    return structured_data

# Function to process the CSV file
def process_csv_file(input_csv_path, output_csv_path):
    # Read the input CSV file
    with open(input_csv_path, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames + ['Key Findings']
        
        # Open the output CSV file for writing (overwrite mode)
        with open(output_csv_path, 'w', encoding='utf-8', newline='') as outfile, \
             open(error_csv_path, 'w', encoding='utf-8', newline='') as errorfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            
            error_writer = csv.DictWriter(errorfile, fieldnames=reader.fieldnames)
            error_writer.writeheader()
            
            for row in reader:
                file_name = row.get('body_part_file_name', 'Unknown')
                report_content = row.get('report_content', '')
                
                if not report_content:
                    print(f"No report content for file {file_name}. Skipping.")
                    continue
                
                # Extract findings from the entire report content
                findings_output = extract_findings(report_content, file_name)
                
                if "Error" in findings_output:
                    print(f"Writing file {file_name} to error.csv due to error.")
                    error_writer.writerow(row)
                    errorfile.flush()
                    continue
                
                # Get findings
                findings = findings_output.get("Findings", "")
                
                # Clean the findings to remove unwanted symbols
                cleaned_findings = clean_findings(findings)
                
                # Add the cleaned findings to the row
                row['Key Findings'] = cleaned_findings
                
                # Write the row to the output CSV
                writer.writerow(row)
                outfile.flush()
                
        print(f"All findings saved to {output_csv_path}")
        print(f"Errors saved to {error_csv_path}")

# Call the function to process the CSV file
process_csv_file(input_csv_path, output_csv_path)
