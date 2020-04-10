import { React, ReactDOM } from 'https://unpkg.com/es-react';
import htm from 'https://unpkg.com/htm?module'
const html = htm.bind(React.createElement)


const plot = () => {
  d3.json('measurements', function(data) {
    data = data.map((m) => {
      m['recorded_at'] = d3.timeParse('%s')(m['recorded_at'])
      return m
    })

    const sensors = Array.from(data.reduce((acc, value) => {
      acc.add(value.sensor)
      return acc
    }, new Set())).sort()

    const sensor_arrays = sensors.map((sensor) => data.filter((m) => m.sensor === sensor))
    
    MG.data_graphic({
      title: "Measurements",
      description: "This is the description.",
      data: sensor_arrays,
      width: 800,
      height: 300,
      target: '#chart',
      legend: sensors,
      legend_target: '.legend',
      x_accessor: 'recorded_at',
      y_accessor: 'temperature',
    });
  });
}

window.onload = plot // () = plot()

// const Foo = () => React.createElement('div', null, `FOO`);
// const Bar = () => React.createElement('div', null, `BAR`);

// window.onload = () => ReactDOM.render(
//   [Foo(), Bar()],
//   document.body
// )
