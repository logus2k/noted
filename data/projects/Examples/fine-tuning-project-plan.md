# Fine-Tuning Project Plan: Job Description Classifier

## 🎯 Project Goal
To fine-tune a small language model (185M parameters) to classify job descriptions, moving beyond simple retrieval to teach the model a specific, reliable classification skill.

## 📋 Classification Schema (Target Labels)
The model must be trained to output discrete, consistent labels based on the following multi-level schema:

### Primary Classification Targets:
1.  **Industry/Domain:** (e.g., Technology, Finance, Healthcare, Education, Retail).
2.  **Seniority Level:** (e.g., Junior, Mid-Level, Senior, Principal, Director).
3.  **Core Function/Role Type:** (e.g., Software Engineer, Data Scientist, Sales Representative, Project Manager).
4.  **Key Skillset:** (e.g., Python, SQL, Cloud Computing, Regulatory Compliance).

### Data Format Target:
The final fine-tuning data will be structured as instruction-response pairs where the input is the raw job description text, and the output is a structured string containing the predicted labels (e.g., "Industry: Technology; Seniority: Senior; Role: Software Engineer; Skills: Python, Cloud Computing").

## 🔍 Summary of Research Findings (Data & Best Practices)

### 1. Data Availability (Low Difficulty)
*   **Job Descriptions:** Publicly available datasets exist on Kaggle and Hugging Face (e.g., "Job Descriptions 2025 - Tech & Non-Tech Roles," "recruitment-dataset-job-descriptions-english"). These are excellent starting points for training.
*   **Customer Feedback:** Large, labeled datasets (e.g., Amazon Review Data) are readily available for sentiment and topic modeling, providing a strong parallel resource.

### 2. Preprocessing Best Practices
To prepare the raw text for fine-tuning, the following pipeline is essential:
*   **Text Cleaning:** Removing noise and unwanted characters (using regex).
*   **Tokenization:** Breaking text into sub-word units the model can process.
*   **Stopword Removal:** Filtering common, low-semantic-value words.
*   **Vectorization/Embedding:** Converting the cleaned text into numerical representations for the model.

### 3. Classification Methods
*   **Standardized Frameworks:** We can leverage governmental classification systems (like EEOC) to ensure the model's categories are industry-standard.
*   **Functional Attributes:** We can define categories based on the actual tasks performed, which is often more useful for a business application.

## ⚙️ Implementation Phase: Technical Workflow

### Phase 2: Data Sourcing and Labeling
*   **Action:** Select a specific, high-quality dataset from the Hugging Face Hub (e.g., "recruitment-dataset-job-descriptions-english").
*   **Goal:** Create a structured dataset where every job description is paired with the multi-level classification labels defined in Phase 1.
*   **Challenge:** If the public dataset lacks the required granularity (e.g., it only has "Engineer" but not "Senior Software Engineer"), we must define a strategy for **synthetic labeling** or **human annotation** to create the necessary training pairs.

### Phase 3: Preprocessing and Training
*   **Action:** Implement the cleaning, tokenization, and structuring pipeline on the selected dataset.
*   **Training Method:** Use Parameter-Efficient Fine-Tuning (PEFT) methods like LoRA or QLoRA to efficiently adapt the 185M parameter model to the classification task, minimizing computational cost.