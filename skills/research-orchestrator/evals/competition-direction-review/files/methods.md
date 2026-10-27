# Public method intake for the fictional competition

Target error: at most 0.35 on the independent review instrument.

A simple threshold family has been built five times. The errors differ by at most 0.002, less than the instrument resolution of 0.01. Changing the threshold again leaves the representation unchanged.

A published method note describes a standalone count-distribution representation followed by a regularized linear decision rule. It retains information that a single threshold discards. It has not been implemented here. The reported score level of about 0.36 was measured on a different sample and is motivation, not local evidence.

Source audit: the local review sample contains two acquisition sources with equal counts. Targets were independently assigned before any candidate was built. Component errors: source alpha 0.30, source beta 0.50; equal weights produce overall error 0.40. Source beta dominates the remaining gap.
