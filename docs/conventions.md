You follow the following conventions:

- **Timestamp unit**: int64 milliseconds
- **Pair canonical form**: EURUSD (no separator)
- **Side convention**: side=+1 means buy base, side=-1 means sell base
- **Quantity**: in *qty* fields, refers to base units for the pair
- **Reference Mid**: $mid_{ref} = (bid_{tob} + ask_{tob}) / 2$
- **Rung sizes**: ordered arrays $[s_1, s_2, ..., s_n]$ in base units for each pair have prices $[p_1, p_2, ..., p_n]$ with potentially different rungs for bid and ask