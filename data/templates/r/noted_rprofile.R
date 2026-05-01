# noted-managed R startup script
# ----------------------------------------------------------------------
# This file is loaded via the R_PROFILE_USER environment variable when
# the ark kernel starts. It activates the renv project at the kernel's
# working directory (the user's project root), while the env vars
# RENV_PATHS_LIBRARY and RENV_PATHS_LOCKFILE redirect renv state to the
# noted-managed environment directory.
#
# Do not edit by hand - this file is overwritten on env creation.

local({
  if (!requireNamespace("renv", quietly = TRUE)) {
    message("[noted] renv not available; skipping activation")
    return(invisible(NULL))
  }
  tryCatch(
    renv::load(project = getwd()),
    error = function(e) {
      message("[noted] renv::load failed: ", conditionMessage(e))
    }
  )
})

# Cell execution helper - wraps source() in withCallingHandlers so that
# errors carry srcref info back to noted for cell line mapping. Each cell
# is written to a per-cell shadow file and executed via this helper.
.noted_run_cell <- function(shadow_path) {
  withCallingHandlers(
    source(shadow_path, keep.source = TRUE, echo = FALSE),
    error = function(e) {
      calls <- sys.calls()
      for (i in seq_along(calls)) {
        sr <- attr(calls[[i]], "srcref")
        if (is.null(sr)) next
        srcfile <- attr(sr, "srcfile")
        if (is.null(srcfile) || is.null(srcfile$filename)) next
        if (srcfile$filename == shadow_path) {
          cat(sprintf(
            "\n[noted-error]{\"file\":\"%s\",\"line\":%d}\n",
            srcfile$filename, sr[1]
          ))
          break
        }
      }
    }
  )
}

# Project root - cells can reference files at the project tree via this
# variable instead of relying on cwd (which is already the project root).
NOTED_PROJECT_ROOT <- Sys.getenv("NOTED_PROJECT_ROOT", unset = NA_character_)
if (!is.na(NOTED_PROJECT_ROOT) && nzchar(NOTED_PROJECT_ROOT)) {
  PROJECT_ROOT <- NOTED_PROJECT_ROOT
}

invisible()
