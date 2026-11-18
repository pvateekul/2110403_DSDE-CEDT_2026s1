# Network Analysis Tool

A powerful interactive web application built with Streamlit for analyzing and visualizing complex networks. This tool provides an intuitive interface for network analysis, supporting various network formats, different layout algorithms, and comprehensive analytical capabilities.

## Features

- **Multiple Data Input Methods**
  - Sample Networks (Karate Club, Les Miserables)
  - Network Generators (Complete, Random, Small World, Scale-free)
  - File Upload (CSV, GML, GraphML formats)

- **Interactive Visualization**
  - Multiple layout algorithms (Spring, Kamada-Kawai, Circular, Random)
  - Node size mapping based on centrality metrics
  - Adjustable visualization parameters
  - Community detection with color coding
  - Interactive zooming and panning
  - Node hover information

- **Network Analysis**
  - Basic network statistics (nodes, edges, density, diameter)
  - Centrality metrics (Degree, Betweenness, Closeness, PageRank)
  - Degree distribution visualization
  - Community detection and analysis

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/network-analysis-tool.git
cd network-analysis-tool
```

2. Install required packages:
```bash
pip install streamlit networkx pandas numpy pyvis matplotlib
```
Or
```bash
pip install -r requirements.txt
```

## Usage

1. Run the Streamlit application:
```bash
streamlit run streamlit_network_analysis.py
```

2. Access the tool through your web browser (typically at `http://localhost:8501`)


## Streamlit Share

The application is also available on https://appnetworkanalysis-bbdpdq3ohya2si4bscrezp.streamlit.app/

### Input Formats

#### CSV Format
- Minimum two columns for source and target nodes
- Example:
```csv
source,target
A,B
B,C
A,C
```

#### GML and GraphML
- Standard GML and GraphML network file formats are supported
- Ensure files follow proper format specifications

## Customization Options

### Visualization
- Layout algorithm selection
- Node size based on different centrality metrics
- Adjustable graph size and node spacing
- Customizable node size ranges
- Adjustable font sizes
- Toggle edge visibility
- Community detection and coloring

### Analysis
- Network statistics
- Centrality metrics
- Degree distribution
- Community analysis

## Dependencies

- streamlit
- networkx
- pandas
- numpy
- pyvis
- matplotlib

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Veera Muangsin

## Acknowledgments

- NetworkX team for the comprehensive network analysis library
- Streamlit team for the excellent web app framework
- Pyvis team for the interactive network visualization capabilities
