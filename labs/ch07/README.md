# Chapter 7 Lab: Graph Retrieval

This lab adds a source-linked graph route beside the Chapter 6 hybrid retriever.
It demonstrates typed query routing, alias resolution, bounded traversal,
temporal contradiction handling, evidence projection, tenant isolation, and
copy-on-write snapshot repair.

Run it with:

```powershell
uv run policyops verify ch07 --profile fixture --junit build/ch07/junit.xml --evidence build/ch07
uv run policyops fault ch07 --scenario all
```

The mandatory fixture profile is deterministic and offline. It does not require
an external graph database or hosted extraction model.
