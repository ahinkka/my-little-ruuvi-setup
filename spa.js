import { h, render } from 'https://unpkg.com/preact@latest?module';
import { useState, useEffect } from 'https://unpkg.com/preact@latest/hooks/dist/hooks.module.js?module';


const serializeHash = (contents) => {
  let keys = Object.keys(contents)
  keys.sort()
  let result = '#'
  let first = true;
  for (const key of keys) {
    let value = contents[key]
    if (first) {
      result += `${key}=${value}`
      first = false
    } else {
      result += `&${key}=${value}`
    }
  }
  return result
}

const parseHash = (hash) => {
  let parts = hash.slice(1).split('&')
  let result = {}
  for (let part of parts) {
    let [key, value] = part.split('=')
    result[key] = value
  }
  return result
}


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


const updateHash = (start, end, measurementType) => {
  const hash = serializeHash({ start, end, measurementType })
  if (hash != window.location.hash) {
    let hashLess = window.location.href
    if (window.location.href.includes('#')) {
      hashLess = window.location.href.split('#')[0]
    }
    window.history.pushState(null, null, hashLess + hash)
  }
}


const Chart = (props) => {
  useEffect(() => {
    plot()
  })
  // }, [])

  return h('div', { id: 'chart' }, [])
}


const App = (props) => {
  const parsedHash = parseHash(window.location.hash)
  const end = parsedHash.end !== undefined ? new Date(parsedHash.end) : new Date()
  const start = parsedHash.start !== undefined ?
	new Date(parsedHash.start) : new Date(end.getTime() - 24 * 60 * 60 * 1000)
  const measurementType = parsedHash.measurementType !== undefined ? parsedHash.measurementType : 'temperature'

  const setEnd = (v) => { updateHash(start, v, measurementType) }
  const setStart = (v) => { updateHash(v, end, measurementType) }
  const setMeasurementType = (v) => { updateHash(start, end, v) }

  return h('div', null, [h(Chart)])
}


window.onload = () => render(App(), document.getElementById('spa'))
