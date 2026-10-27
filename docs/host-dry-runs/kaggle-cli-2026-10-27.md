# Kaggle CLI syntax — 2026-10-27

Only the following three commands were run. All exited 0. No account operation was attempted and no credentials were read by the builder. Help verifies syntax, not authentication, authorization or remote success. Other adapter commands remain unverified.

```text
> kaggle --version
Kaggle CLI 2.2.4
> kaggle competitions submit --help
usage: kaggle competitions submit [-h] [-f FILE_NAME] [-k KERNEL] -m MESSAGE
                                  [-v VERSION] [-q] [--sandbox]
                                  [competition]

options:
  -h, --help            show this help message and exit
  competition           Competition URL suffix (use "kaggle competitions list" to show options)
                        If empty, the default competition will be used (use "kaggle config set competition")"
  -f FILE_NAME, --file FILE_NAME
                        File for upload (full path), or the name of the output file produced by a kernel (for code competitions)
  -k KERNEL, --kernel KERNEL
                        Name of kernel (notebook) to submit to a code competition
  -m MESSAGE, --message MESSAGE
                        Message describing this submission
  -v VERSION, --version VERSION
                        Version of kernel to submit to a code competition, e.g. "3"
  -q, --quiet           Suppress printing information about the upload/download progress
  --sandbox             Mark submission as a sandbox submission (competition hosts/admins only)
> kaggle competitions submissions --help
usage: kaggle competitions submissions [-h] [-v | --format OUTPUT_FORMAT] [-q]
                                       [--page-size PAGE_SIZE]
                                       [--page-token PAGE_TOKEN]
                                       [competition]

options:
  -h, --help            show this help message and exit
  competition           Competition URL suffix (use "kaggle competitions list" to show options)
                        If empty, the default competition will be used (use "kaggle config set competition")"
  -v, --csv             Print results in CSV format (if not set print in table format)
  --format OUTPUT_FORMAT
                        Print results in selected format (csv, table, json). For details on advanced options, see
                        https://github.com/Kaggle/kaggle-cli/blob/main/docs/output_format.md
  -q, --quiet           Suppress printing information about the upload/download progress
  --page-size PAGE_SIZE
                        Number of items to show on a page. Default size is 20, max is 200
  --page-token PAGE_TOKEN
                        Page token for results paging.
```
