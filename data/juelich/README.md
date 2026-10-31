# Jülich experiment data (for model validation)

From the Pedestrian Dynamics Data Archive, Forschungszentrum Jülich
(https://ped.fz-juelich.de/da), licensed CC BY 4.0. Only `metadata.json` is kept in
git; download the trajectories with the commands below.

| Folder | Experiment | DOI | Used for |
|---|---|---|---|
| `bottleneck2/` | Bottleneck, Caserne (Düsseldorf 2006), runs `b090`–`b250`: widths 0.9–2.5 m, length 4 m, ~175 people | [10.34735/ped.2006.2](https://doi.org/10.34735/ped.2006.2) | flow vs width |
| `unidir_open/` | Hermes unidirectional corridor, open boundary (Düsseldorf 2009), corridors 1.8/2.4/3.0 m | [10.34735/ped.2009.14](https://doi.org/10.34735/ped.2009.14) | speed–density |

Trajectory format: `id frame x y [z]`, centimetres; 25 fps (bottleneck), 16 fps (corridor).
Each run's geometry is the `wkt_geometry` in `metadata.json`.

```sh
cd data/juelich
B=http://ped.fz-juelich.de/experiments/2006.11.27_Duesseldorf_Casern/data/eg
U=http://ped.fz-juelich.de/experiments/2009.05.12_Duesseldorf_Messe_Hermes/data/zip
curl -L -o bottleneck2/trajectories_txt.zip $B/2006bottleneck2_trajectories_txt.zip
curl -L -o unidir_open/trajectories_txt.zip $U/2009unidirectional_open_trajectories_txt.zip
(cd bottleneck2 && unzip -o trajectories_txt.zip) && (cd unidir_open && unzip -o trajectories_txt.zip)
```

Please cite (as the archive asks):
- Seyfried et al. (2010), Enhanced empirical data for the fundamental diagram and the flow through
  bottlenecks, PED 2008, Springer, 145–156. Data: DFG grants KL 1873/1-1 and SE 1789/1-1.
- Zhang, Klingsch, Schadschneider, Seyfried (2011), Transitions in pedestrian fundamental diagrams of
  straight corridors and T-junctions, J. Stat. Mech. P06004. Data: BMBF project Hermes.
