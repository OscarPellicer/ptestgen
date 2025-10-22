## Script to generate exams using R/exams package
## This script requires R and the exams package to be installed

# Install optparse if not already installed
if(!require("optparse")) install.packages("optparse", repos = "http://cran.rstudio.com/")
library("optparse")

# Define command line options
option_list <- list(
  make_option(c("--questions-dir"), type="character", default="questions",
              help="Directory with Rmd question files [default %default]", metavar="character"),
  make_option(c("--output-dir"), type="character", default="output",
              help="Directory to save exam outputs [default %default]", metavar="character"),
  make_option(c("--n-models"), type="integer", default=4,
              help="Number of exam models to generate [default %default]", metavar="integer"),
  make_option(c("--language"), type="character", default="es",
              help="Language for the exam (e.g., 'es', 'en', 'ca') [default %default]", metavar="character"),
  make_option(c("--logo"), type="character", default="logo_uv.jpg",
              help="Path to the logo file. Empty string for no logo. [default %default]", metavar="character"),
  make_option(c("--date"), type="character", default="2025-04-01",
              help="Date of the exam (YYYY-MM-DD) [default %default]", metavar="character"),
  make_option(c("--exam-title"), type="character", default="Auditoría de Algoritmos - Examen Final",
              help="Title of the exam [default %default]", metavar="character"),
  make_option(c("--course"), type="character", default="MU Sociedad Digital",
              help="Course name [default %default]", metavar="character"),
  make_option(c("--institution"), type="character", default="Universitat de València",
              help="Institution name [default %default]", metavar="character"),
  make_option(c("--seed"), type="integer", default=12345,
              help="Seed for reproducibility [default %default]", metavar="integer"),
  make_option(c("--max-questions"), type="integer", default=45,
              help="Maximum number of questions per exam [default %default]", metavar="integer"),
  make_option(c("--intro-text"), type="character", 
              default='\\underline{Instrucciones:}\\n\\begin{itemize}\\n\\item \\textbf{Está completamente prohibido tener dispositivos electrónicos o apuntes durante la realización del examen}\\n\\item \\textbf{No utilizar tipex para corregir}\\n\\item \\textbf{\\underline{Penalización}: Cada respuesta errónea puntúa -1/3 puntos}\\n\\end{itemize}',
              help="Introductory text for the exam. Use '\\n' for newlines. [default %default]", metavar="character")
)

opt_parser <- OptionParser(option_list=option_list)
opts <- parse_args(opt_parser)

# Install required packages if not already installed
if(!require("exams")) {
  cat("Installing 'exams' package...\n")
  install.packages("exams", repos = "http://cran.rstudio.com/")
}
if(!require("tinytex")) {
  cat("Installing 'tinytex' package...\n")
  install.packages("tinytex", repos = "http://cran.rstudio.com/")
}

# Ensure TinyTeX is installed and has the necessary packages
tryCatch({
    if(!tinytex::tinytex_root()) {
        cat("TinyTeX not found, installing it...\n")
        tinytex::install_tinytex()
    }
    cat("Checking for Spanish hyphenation package...\n")
    tinytex::tlmgr_install("hyphen-spanish")
}, error = function(e) {
    cat("An error occurred during TinyTeX setup or package installation: ", e$message, "\n")
    cat("Please check your internet connection and R environment permissions.\n")
})

if(!require("optparse")) {
  cat("Installing 'optparse' package...\n")
  install.packages("optparse", repos = "http://cran.rstudio.com/")
}

library("exams")
library("knitr")

knitr::opts_chunk$set(cache = FALSE)

# Use parsed options
questions_dir_path <- opts$`questions-dir`
output_dir_path <- opts$`output-dir`

# Get all Rmd files in the questions directory
question_files <- list.files(questions_dir_path, pattern = "\\.Rmd$", full.names = TRUE)

cat("Total number of available questions:", length(question_files), "in dir:", questions_dir_path, "\n")

MAX_QUESTIONS <- opts$`max-questions`

# Function to generate exams
generate_exam_set <- function() {
  if(length(question_files) == 0) {
    cat("Error: No .Rmd question files found in directory:", questions_dir_path, "\n")
    cat("Please ensure the --questions-dir argument is correct and contains .Rmd files.\n")
    stop("No question files found.")
  }

  # Set seed for sampling questions if needed (before sample() call)
  set.seed(opts$seed)
  
  if(length(question_files) > MAX_QUESTIONS) {
    cat("Note: Only", MAX_QUESTIONS, "questions can be used per exam out of",
        length(question_files), "available questions.\n")
    cat("Randomly sampling", MAX_QUESTIONS, "questions using seed:", opts$seed, ".\n")
    sampled_questions <- sample(question_files, MAX_QUESTIONS)
  } else {
    sampled_questions <- question_files
    cat("Using all", length(sampled_questions), "available questions.\n")
  }
  
  cat("Number of questions being used:", length(sampled_questions), "\n")
  
  # Set the seed for exams2nops for reproducibility of exam versions
  set.seed(opts$seed)

  if (!dir.exists(output_dir_path)) {
    cat("Creating output directory:", output_dir_path, "\n")
    dir.create(output_dir_path, recursive = TRUE)
  }

  logo_path_arg <- opts$logo
  actual_logo_path <- NULL # Default to no logo

  if (nchar(logo_path_arg) > 0) { # If a logo path is provided
    if (file.exists(logo_path_arg)) {
      actual_logo_path <- logo_path_arg
      cat("Using logo file:", actual_logo_path, "\n")
    } else {
      cat("Warning: Logo file not found at '", logo_path_arg, "'.\n")
      cat("Working directory:", getwd(), "\n")
      cat("Proceeding without logo. Ensure the path is correct or the file is accessible.\n")
      # actual_logo_path remains NULL
    }
  } else {
    cat("No logo file specified. Proceeding without logo.\n")
    # actual_logo_path remains NULL
  }

  # Determine babel language option for header
  babel_lang_option <- switch(opts$language,
                            "es" = "spanish",
                            "ca" = "catalan",
                            "en" = "english",
                            "spanish") # Default
  exam_header <- paste0("\\usepackage[", babel_lang_option, "]{babel}")
  cat("Using LaTeX header:", exam_header, "\n")

  # Process intro text: replace literal '\n' with actual newlines
  intro_text_processed <- gsub("\\\\n", "\n", opts$`intro-text`)
  intro_for_exams <- strsplit(intro_text_processed, "\n")[[1]]

  exams2nops(
    file = sampled_questions,
    n = opts$`n-models`,
    intro = intro_for_exams,
    language = opts$language,
    dir = output_dir_path,
    date = opts$date,
    name = "exam",
    title = opts$`exam-title`,
    course = opts$course,
    institution = opts$institution,
    logo = actual_logo_path, # Use the resolved logo path
    replacement = FALSE,
    reglength = 8,
    duplex = TRUE,
    samepage = TRUE,
    twocolumn = FALSE,
    fonts = NULL,
    header = exam_header,
    # encoding = "UTF-8",
    # blank = 1,
    # keep_tex = TRUE,
    texdir = output_dir_path,
  )
  
  sampled_questions_list_file <- file.path(output_dir_path, "sampled_questions.txt")
  cat("Questions used in the exam:\n", file = sampled_questions_list_file)
  for(i in 1:length(sampled_questions)) {
    cat(paste0(i, ". ", basename(sampled_questions[i]), "\n"), 
        file = sampled_questions_list_file, append = TRUE)
  }
  cat("Exam generation complete. Output in:", output_dir_path, "\n")
}

# Call the main function
generate_exam_set()