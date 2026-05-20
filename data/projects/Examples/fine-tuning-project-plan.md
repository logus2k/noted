# Research Workspace

## Goal

Research the best practices and datasets for fine-tuning a small language model to classify job descriptions.

## Acceptance Criteria

- [ ] Identify key classification categories (e.g., industry, seniority, required skills).
- [ ] List publicly available datasets of job descriptions suitable for classification tasks.
- [ ] Outline the necessary data preprocessing steps (e.g., tokenization, cleaning) for job description data.

## Review Notes

### Iteration 1

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: The Findings section is empty. Please begin your research by identifying key classification categories, listing suitable datasets, and outlining the necessary data preprocessing steps.

### Iteration 1

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: The current findings focus on customer feedback and general review datasets. Please pivot your research to find classification categories (industry, seniority, skills) and publicly available datasets specifically for job descriptions. Also, outline standard preprocessing steps for job description text.

### Iteration 1

- verdict: **ready_for_user**
- criteria met: 3/3

### Final state (✓ Accepted, iteration 1)

- detail: User accepted the research as complete.

### Iteration 2

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

### Iteration 2

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

### Iteration 3

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

### Iteration 3

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

### Iteration 4

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

### Iteration 4

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

### Iteration 5

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

### Iteration 5

- verdict: **iterate**
- criteria met: 0/3
- reviewer notes: Reviewer failed to produce valid JSON after 3 attempts. Continuing research; please address all unmet criteria.

## Findings

_(empty — researcher will populate this section)_


### Common Categories of Product Feedback

Customer feedback can be categorized in various ways to provide actionable insights for product improvement and customer experience enhancement [source: https://www.forsta.com/resources/blog/types-of-customer-feedback/]. Common categories identified include:

*   **Product Feedback:** This is the staple type of feedback, focusing directly on the product itself [source: https://www.forsta.com/resources/blog/types-of-customer-feedback/].
*   **Usability/Experience:** Feedback related to how easy or intuitive the product is to use [source: https://www.savio.io/blog/how-to-categorize-product-feedback-effectively/].
*   **Performance:** Comments on how well the product functions, including speed, reliability, and stability [source: https://blog.hubspot.com/service/types-of-customer-feedback-examples].
*   **Pricing/Value:** Opinions regarding the cost of the product relative to its perceived value [source: https://www.commercepundit.com/blog/different-types-of-customer-feedback/].

Categorization is an ongoing process that helps businesses improve products and enhance customer satisfaction [source: https://www.savio.io/blog/how-to-categorize-product-feedback-effectively/].

### Publicly Available Datasets for Customer Review Analysis

Several large-scale and curated datasets are available for training NLP models for sentiment analysis and topic modeling:

*   **Amazon Review Data:** This is noted as one of the largest publicly available labeled sentiment analysis datasets, containing over 230 million customer reviews spanning from 1996 to 2018 [source: https://www.marketingscoop.com/ai/sentiment-analysis-dataset/].
*   **Kaggle:** Kaggle is mentioned as a source for various sentiment analysis and NLP datasets [source: https://www.upgrad.com/blog/established-datasets-for-sentiment-analysis/].
*   **General Resources:** Other resources include general user review datasets for machine learning and various top-rated sentiment analysis datasets updated for 2025 [source: https://crawlfeeds.com/posts/user-reviews-datasets-for-sentiment-analysis-and-machine-learning] and [source: https://www.interviewquery.com/p/sentiment-analysis-projects-and-datasets].

### Key Classification Categories and Attributes

Job description classification can be approached through standardized governmental frameworks or through functional categories relevant to the target task.

*   **Standardized Frameworks:** Government agencies utilize formal classification systems. For example, the EEOC employs 10 major job categories for EEO-1 reporting, which describe required skills and training [source: https://www.berkshireassociates.com/hubfs/EEOC%20CLASSIFICATION_OF_EMPLOYEES_INTO_JOB_CATEGORIES.pdf]. Similarly, federal systems define classifications based on job class specifications, detailing the kind of work performed [source: https://mn.gov/mmb/employee-relations/career-paths-and-families/classification-specifications/].
*   **Functional Attributes:** A job description generally contains attributes such as the definition of the classification, minimum qualifications, and typical tasks [source: https://www.calhr.ca.gov/about-calhr/divisions-programs/personnel-management/job-descriptions/]. For the purpose of fine-tuning, key classification targets could include **Industry**, **Seniority Level** (e.g., Junior, Senior, Manager), **Required Skills**, and **Role Type**.

### Publicly Available Job Description Datasets

Several public datasets are available for training and testing job description classification models:

*   **Kaggle Dataset:** A synthetic dataset titled "Job Descriptions 2025 - Tech & Non-Tech Roles" contains 1,100 synthetic job descriptions spanning 55 diverse roles, suitable for NLP research [source: https://www.kaggle.com/datasets/adityarajsrv/job-descriptions-2025-tech-and-non-tech-roles].
*   **Hugging Face Dataset:** The "recruitment-dataset-job-descriptions-english" includes various attributes such as position titles, job descriptions, company names, and experience requirements [source: https://huggingface.co/datasets/lang-uk/recruitment-dataset-job-descriptions-english/blob/main/README.md].
*   **Academic Datasets:** Research papers, such as those focusing on competence-level classification, provide specialized datasets for resume and job description screening [source: https://southnlp.github.io/southnlp2024/papers/southnlp2024-poster-58.pdf].
*   **General NLP Repositories:** Resources like the niderhoff/nlp-datasets GitHub repository provide a list of free/public domain text data for NLP tasks [source: https://github.com/niderhoff/nlp-datasets].

### Fine-Tuning Best Practices and Preprocessing Overview

For fine-tuning a small language model for this task, several best practices apply:

*   **Methodology Selection:** Fine-tuning can employ supervised, unsupervised, or instruction-based approaches, depending on the data and desired outcome [source: https://arxiv.org/html/2408.13296v1]. Techniques like Parameter-Efficient Fine-Tuning (PEFT) and LoRA are common methods for efficient training [source: https://www.databricks.com/blog/llm-fine-tuning].
*   **Data Pipeline:** A structured pipeline is recommended, covering data preparation, training, and deployment [source: https://arxiv.org/html/2408.13296v1].
*   **Preprocessing/Data Handling:** While specific preprocessing steps (tokenization, cleaning) were not detailed in the search snippets, the general best practice involves careful dataset curation and managing the separation of training and evaluation sets [source: https://medium.com/@kangjunong1/llm-classification-tasks-best-practices-youve-never-heard-of-7157ac7a4154, https://developers.openai.com/api/docs/guides/fine-tuning-best-practices].

### Key Classification Categories for Job Descriptions

Job descriptions can be classified using various frameworks depending on the goal (e.g., HR compliance, skill matching, or industry analysis). Common classification methods include:

*   **By Functional Duties/Responsibilities:** Grouping jobs based on similar tasks and the kind of work performed (e.g., administrative, engineering, sales) [source: https://mn.gov/mmb/employee-relations/career-paths-and-families/classification-specifications/].
*   **By Minimum Qualifications/Skills:** Classifying roles based on the required level of education, experience, or specific skills needed to apply for the job [source: https://www.calhr.ca.gov/about-calhr/divisions-programs/personnel-management/job-descriptions/].
*   **By Occupational Grouping:** Utilizing standardized categories, such as the 10 major job categories used by the EEOC (e.g., Executive, Clerical, Laborer) for reporting purposes [source: https://www.berkshireassociates.com/hubfs/EEOC%20CLASSIFICATION_OF_EMPLOYEES_INTO_JOB_CATEGORIES.pdf].

### Data Preprocessing Steps for Job Description NLP

To prepare raw job description text for fine-tuning an NLP model, several preprocessing steps are essential to transform the data into a usable format:

1.  **Text Cleaning:** This initial step involves removing noise, unwanted characters, and irrelevant elements from the raw text to ensure the data is structured and clean for analysis. Regular expressions (regex) are a common tool used for this process [source: https://www.geeksforgeeks.org/nlp/text-preprocessing-for-nlp-tasks/].
2.  **Tokenization:** The process of breaking down continuous text into smaller, manageable units (tokens, usually words or sub-words) that the model can process [source: https://pkeilbach.github.io/htwg-practical-nlp/lectures/preprocessing/].
3.  **Stopword Removal:** Filtering out common words (like "the," "a," "is") that appear frequently but carry little semantic weight for classification tasks [source: https://github.com/YULINHEEE/NLP-text-preprocessing-and-classification].
4.  **Vectorization/Embedding:** The final step is converting the cleaned and tokenized text into numerical representations (embeddings) that the machine learning model can understand and process [source: https://pkeilbach.github.io/htwg-practical-nlp/lectures/preprocessing/].

### Publicly Available Datasets

While general NLP datasets are available (e.g., Amazon Review Data, Kaggle resources), specific, large-scale, publicly available datasets of *job descriptions* suitable for classification were not identified in the current search iteration. This remains a gap to be addressed.

### Key Classification Categories and Attributes

Job description classification can be approached through standardized governmental frameworks or through functional categories relevant to the target task.

*   **Standardized Frameworks:** Government agencies utilize formal classification systems. For example, the EEOC employs 10 major job categories for EEO-1 reporting, which describe required skills and training [source: https://www.berkshireassociates.com/hubfs/EEOC%20CLASSIFICATION_OF_EMPLOYEES_INTO_JOB_CATEGORIES.pdf]. Similarly, federal systems define classifications based on job class specifications, detailing the kind of work performed [source: https://mn.gov/mmb/employee-relations/career-paths-and-families/classification-specifications/].
*   **Functional Attributes:** A job description generally contains attributes such as the definition of the classification, minimum qualifications, and typical tasks [source: https://www.calhr.ca.gov/about-calhr/divisions-programs/personnel-management/job-descriptions/]. For the purpose of fine-tuning, key classification targets could include **Industry**, **Seniority Level** (e.g., Junior, Senior, Manager), **Required Skills**, and **Role Type**.

### Publicly Available Job Description Datasets

Several public datasets are available for training and testing job description classification models:

*   **Kaggle Dataset:** A synthetic dataset titled "Job Descriptions 2025 - Tech & Non-Tech Roles" contains 1,100 synthetic job descriptions spanning 55 diverse roles, suitable for NLP research [source: https://www.kaggle.com/datasets/adityarajsrv/job-descriptions-2025-tech-and-non-tech-roles].
*   **Hugging Face Dataset:** The "recruitment-dataset-job-descriptions-english" includes various attributes such as position titles, job descriptions, company names, and experience requirements [source: https://huggingface.co/datasets/lang-uk/recruitment-dataset-job-descriptions-english/blob/main/README.md].
*   **Academic Datasets:** Research papers, such as those focusing on competence-level classification, provide specialized datasets for resume and job description screening [source: https://southnlp.github.io/southnlp2024/papers/southnlp2024-poster-58.pdf].
*   **General NLP Repositories:** Resources like the niderhoff/nlp-datasets GitHub repository provide a list of free/public domain text data for NLP tasks [source: https://github.com/niderhoff/nlp-datasets].

### Fine-Tuning Best Practices and Preprocessing Overview

For fine-tuning a small language model for this task, several best practices apply:

*   **Methodology Selection:** Fine-tuning can employ supervised, unsupervised, or instruction-based approaches, depending on the data and desired outcome [source: https://arxiv.org/html/2408.13296v1]. Techniques like Parameter-Efficient Fine-Tuning (PEFT) and LoRA are common methods for efficient training [source: https://www.databricks.com/blog/llm-fine-tuning].
*   **Data Pipeline:** A structured pipeline is recommended, covering data preparation, training, and deployment [source: https://arxiv.org/html/2408.13296v1].
*   **Preprocessing/Data Handling:** While specific preprocessing steps (tokenization, cleaning) were not detailed in the search snippets, the general best practice involves careful dataset curation and managing the separation of training and evaluation sets [source: https://medium.com/@kangjunong1/llm-classification-tasks-best-practices-youve-never-heard-of-7157ac7a4154, https://developers.openai.com/api/docs/guides/fine-tuning-best-practices].

### Key Classification Categories for Job Descriptions

Job descriptions can be classified using various frameworks depending on the goal (e.g., HR compliance, skill matching, or industry analysis). Common classification methods include:

*   **By Functional Duties/Responsibilities:** Grouping jobs based on similar tasks and the kind of work performed (e.g., administrative, engineering, sales) [source: https://mn.gov/mmb/employee-relations/career-paths-and-families/classification-specifications/].
*   **By Minimum Qualifications/Skills:** Classifying roles based on the required level of education, experience, or specific skills needed to apply for the job [source: https://www.calhr.ca.gov/about-calhr/divisions-programs/personnel-management/job-descriptions/].
*   **By Occupational Grouping:** Utilizing standardized categories, such as the 10 major job categories used by the EEOC (e.g., Executive, Clerical, Laborer) for reporting purposes [source: https://www.berkshireassociates.com/hubfs/EEOC%20CLASSIFICATION_OF_EMPLOYEES_INTO_JOB_CATEGORIES.pdf].

### Data Preprocessing Steps for Job Description NLP

To prepare raw job description text for fine-tuning an NLP model, several preprocessing steps are essential to transform the data into a usable format:

1.  **Text Cleaning:** This initial step involves removing noise, unwanted characters, and irrelevant elements from the raw text to ensure the data is structured and clean for analysis. Regular expressions (regex) are a common tool used for this process [source: https://www.geeksforgeeks.org/nlp/text-preprocessing-for-nlp-tasks/].
2.  **Tokenization:** The process of breaking down continuous text into smaller, manageable units (tokens, usually words or sub-words) that the model can process [source: https://pkeilbach.github.io/htwg-practical-nlp/lectures/preprocessing/].
3.  **Stopword Removal:** Filtering out common words (like "the," "a," "is") that appear frequently but carry little semantic weight for classification tasks [source: https://github.com/YULINHEEE/NLP-text-preprocessing-and-classification].
4.  **Vectorization/Embedding:** The final step is converting the cleaned and tokenized text into numerical representations (embeddings) that the machine learning model can understand and process [source: https://pkeilbach.github.io/htwg-practical-nlp/lectures/preprocessing/].

### Publicly Available Datasets

While general NLP datasets are available (e.g., Amazon Review Data, Kaggle resources), specific, large-scale, publicly available datasets of *job descriptions* suitable for classification were not identified in the current search iteration. This remains a gap to be addressed.

### Key Classification Categories for Job Descriptions

Job descriptions can be classified using various frameworks depending on the goal (e.g., HR compliance, skill matching, or industry analysis). Common classification methods include:

*   **By Functional Duties/Responsibilities:** Grouping jobs based on similar tasks and the kind of work performed (e.g., administrative, engineering, sales) [source: https://mn.gov/mmb/employee-relations/career-paths-and-families/classification-specifications/].
*   **By Minimum Qualifications/Skills:** Classifying roles based on the required level of education, experience, or specific skills needed to apply for the job [source: https://www.calhr.ca.gov/about-calhr/divisions-programs/personnel-management/job-descriptions/].
*   **By Occupational Grouping:** Utilizing standardized categories, such as the 10 major job categories used by the EEOC (e.g., Executive, Clerical, Laborer) for reporting purposes [source: https://www.berkshireassociates.com/hubfs/EEOC%20CLASSIFICATION_OF_EMPLOYEES_INTO_JOB_CATEGORIES.pdf].

### Data Preprocessing Steps for Job Description NLP

To prepare raw job description text for fine-tuning an NLP model, several preprocessing steps are essential to transform the data into a usable format:

1.  **Text Cleaning:** This initial step involves removing noise, unwanted characters, and irrelevant elements from the raw text to ensure the data is structured and clean for analysis. Regular expressions (regex) are a common tool used for this process [source: https://www.geeksforgeeks.org/nlp/text-preprocessing-for-nlp-tasks/].
2.  **Tokenization:** The process of breaking down continuous text into smaller, manageable units (tokens, usually words or sub-words) that the model can process [source: https://pkeilbach.github.io/htwg-practical-nlp/lectures/preprocessing/].
3.  **Stopword Removal:** Filtering out common words (like "the," "a," "is") that appear frequently but carry little semantic weight for classification tasks [source: https://github.com/YULINHEEE/NLP-text-preprocessing-and-classification].
4.  **Vectorization/Embedding:** The final step is converting the cleaned and tokenized text into numerical representations (embeddings) that the machine learning model can understand and process [source: https://pkeilbach.github.io/htwg-practical-nlp/lectures/preprocessing/].

### Publicly Available Datasets

While general NLP datasets are available (e.g., Amazon Review Data, Kaggle resources), specific, large-scale, publicly available datasets of *job descriptions* suitable for classification were not identified in the current search iteration. This remains a gap to be addressed.