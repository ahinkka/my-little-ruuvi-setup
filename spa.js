import { React, ReactDOM } from 'https://unpkg.com/es-react';
import htm from 'https://unpkg.com/htm?module'
const html = htm.bind(React.createElement)


const plot = () => {
  d3.json('measurement', function(data) {
    data = data.map((m) => {
      m['recorded_at'] = d3.timeParse('%s')(m['recorded_at'])
      return m
    })
    
    MG.data_graphic({
      title: "Measurements",
      description: "This is the description.",
      data: data,
      width: 600,
      height: 200,
      right: 40,
      target: '#chart',
      legend: ['Line 1','Line 2','Line 3'],
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

// d3.json('data/fake_users2.json', function(data) {
//     for (var i = 0; i < data.length; i++) {
//         data[i] = MG.convert.date(data[i], 'date');
//     }

//     MG.data_graphic({
//         title: "Multi-Line Chart",
//         description: "This line chart contains multiple lines.",
//         data: data,
//         width: 600,
//         height: 200,
//         right: 40,
//         target: '#fake_users2',
//         legend: ['Line 1','Line 2','Line 3'],
//         legend_target: '.legend'
//     });
// });
