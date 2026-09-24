import { Chart, registerables } from "chart.js";

Chart.register(...registerables);
window.PathGenChart = Chart;
