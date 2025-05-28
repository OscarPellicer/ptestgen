import os
import shutil
import sys
import glob
import logging
from typing import Optional

def _is_executable(path: str) -> bool:
    """Checks if a path is an executable file."""
    return os.path.isfile(path) and os.access(path, os.X_OK)

def _find_rscript_executable(r_exec_param: Optional[str]) -> Optional[str]:
    """
    Tries to find a valid Rscript executable.
    Search order:
    1. If r_exec_param is a specific path (not "Rscript" or "Rscript.exe"), validate and use it.
       If invalid, returns None without further search.
    2. If r_exec_param is None or a generic name ("Rscript", "Rscript.exe"):
       a. Check PATH for 'Rscript.exe' (Windows) or 'Rscript'.
       b. Check common installation directories for Windows, macOS, and Linux.
    """
    if r_exec_param and r_exec_param.lower() not in ["rscript", "rscript.exe"]:
        abs_path = os.path.abspath(r_exec_param)
        if _is_executable(abs_path):
            logging.info(f"Using user-specified Rscript path: {abs_path}")
            return abs_path
        else:
            logging.warning(f"User-specified Rscript path '{r_exec_param}' (resolved to '{abs_path}') is not a valid executable. No further search will be performed.")
            return None

    default_exec_names = ["Rscript.exe", "Rscript"] if sys.platform == "win32" else ["Rscript"]
    for name in default_exec_names:
        found_in_path = shutil.which(name)
        if found_in_path and _is_executable(found_in_path):
            logging.info(f"Found Rscript in PATH: {found_in_path}")
            return found_in_path

    common_paths = []
    if sys.platform == "win32":
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        r_base_paths = [os.path.join(program_files, "R"), os.path.join(program_files_x86, "R")]
        for r_base in r_base_paths:
            if os.path.isdir(r_base):
                version_dirs = sorted(glob.glob(os.path.join(r_base, "R-*")), reverse=True)
                for r_version_dir in version_dirs:
                    for bin_subdir in ["bin", os.path.join("bin", "x64"), os.path.join("bin", "i386")]:
                        common_paths.append(os.path.join(r_version_dir, bin_subdir, "Rscript.exe"))
    elif sys.platform == "darwin":
        common_paths.extend([
            "/usr/local/bin/Rscript",
            "/Library/Frameworks/R.framework/Versions/Current/Resources/bin/Rscript",
            "/Library/Frameworks/R.framework/Resources/bin/Rscript",
        ])
        homebrew_brew_path = shutil.which("brew")
        if homebrew_brew_path:
            homebrew_prefix_dir = os.path.dirname(os.path.dirname(homebrew_brew_path))
            common_paths.append(os.path.join(homebrew_prefix_dir, "bin", "Rscript"))
            common_paths.append(os.path.join(homebrew_prefix_dir, "opt", "r", "bin", "Rscript"))
        else:
            common_paths.append("/opt/homebrew/bin/Rscript")
            common_paths.append("/usr/local/opt/r/bin/Rscript")
    else: # Linux/other Unix
        common_paths.extend(["/usr/bin/Rscript", "/usr/local/bin/Rscript"])
        if os.path.isdir("/opt/R"):
            opt_r_paths = sorted(glob.glob("/opt/R/*/bin/Rscript"), reverse=True)
            common_paths.extend(opt_r_paths)

    for path_to_check in common_paths:
        if _is_executable(path_to_check):
            logging.info(f"Found Rscript in common location: {path_to_check}")
            return path_to_check
            
    logging.warning("Rscript executable could not be located automatically.")
    return None 