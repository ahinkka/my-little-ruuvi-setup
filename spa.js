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


const plot = (start, end, measurementType) => {
  d3.json('measurements' +
	  `?start=${Math.floor(start.getTime() / 1000)}` +
	  `&end=${Math.floor(end.getTime() / 1000)}` +
	  `&measurementType=${measurementType}`,
    function(data) {
      data = data.map((m) => {
	m['recorded_at'] = d3.timeParse('%s')(m['recorded_at'])
	return m
      })

      const sensors = Array.from(data.reduce((acc, value) => {
	acc.add(value.sensor)
	return acc
      }, new Set())).sort()

      const sensorArrays = sensors.map((sensor) => data.filter((m) => m.sensor === sensor))

      let yax_unit
      if (measurementType == 'temperature') {
	yax_unit = '°C'
      } else if (measurementType == 'humidity') {
	yax_unit = '%'
      } else if (measurementType == 'pressure') {
	yax_unit = 'P'
      } else if (measurementType == 'battery_voltage') {
	yax_unit = 'V'
      } else if (measurementType == 'tx_power') {
	yax_unit = 'dBm'
      }

      const viewportWidth = (window.innerWidth > 0) ? window.innerWidth : screen.width
      MG.data_graphic({
	data: sensorArrays,
	width: Math.min(1150, viewportWidth),
	height: 400,
	target: '#chart',
	legend: sensors,
	legend_target: '.legend',
	x_accessor: 'recorded_at',
	y_accessor: measurementType,
	aggregate_rollover: true,
	brush: 'x',
	min_y_from_data: true,
	yax_units: yax_unit,
	yax_units_append: true
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

const QuickChooser = (props) => {
  const { timeCallback, periodMs, presentedPeriod } = props
  return h('button', {
    onClick: () => timeCallback(new Date(new Date() - periodMs), new Date())
  }, presentedPeriod)
}


const MeasurementTypeDropdown = (props) => {
  const { measurementTypeCallback, measurementType } = props
  // return h('ul', {
  //   onClick: () => timeCallback(new Date(new Date() - periodMs), new Date())
  // }, presentedPeriod)

  return h('select', { onChange: (e) => {
    const select = e.target
    measurementTypeCallback(select.children[select.selectedIndex].value)
  }}, [
    h('option', { value: 'temperature', selected: measurementType == 'temperature' }, 'Temperature'),
    h('option', { value: 'humidity', selected: measurementType == 'humidity' }, 'Humidity'),
    h('option', { value: 'pressure', selected: measurementType == 'pressure' }, 'Pressure'),
    h('option', { value: 'battery_voltage', selected: measurementType == 'battery_voltage' }, 'Battery voltage'),
    h('option', { value: 'tx_power', selected: measurementType == 'tx_power' }, 'TX Power'),
  ])
}


const Header = (props) => {
  const { timeCallback, measurementType, measurementTypeCallback } = props
  const millisInHour = 60 * 60 * 1000
  return h('div', { className: 'row', style: { marginTop: '25px' }}, [
    h('h3', { className: 'col col-lg-4' }, 'Measurement browser'),
    h('div', { className: 'col align-middle' },
      [h('div', { className: 'float-right'}, 'Show last')]),
    h(QuickChooser, { timeCallback, periodMs: 1 * millisInHour, presentedPeriod: '1h' }),
    h(QuickChooser, { timeCallback, periodMs: 3 * millisInHour, presentedPeriod: '3h' }),
    h(QuickChooser, { timeCallback, periodMs: 6 * millisInHour, presentedPeriod: '6h' }),
    h(QuickChooser, { timeCallback, periodMs: 12 * millisInHour, presentedPeriod: '12h' }),
    h(QuickChooser, { timeCallback, periodMs: 24 * millisInHour, presentedPeriod: '24h' }),
    h(QuickChooser, { timeCallback, periodMs: 2 * 24 * millisInHour, presentedPeriod: '2d' }),
    h(QuickChooser, { timeCallback, periodMs: 3 * 24 * millisInHour, presentedPeriod: '3d' }),
    h(QuickChooser, { timeCallback, periodMs: 7 * 24 * millisInHour, presentedPeriod: '7d' }),
    h(MeasurementTypeDropdown, { measurementType, measurementTypeCallback })
  ])
}


const Chart = (props) => {
  const { start, end, measurementType } = props
  useEffect(() => {
    plot(start, end, measurementType)
  }, [start, end, measurementType])

  return h('div', { id: 'chart' }, [])
}


const App = (props) => {
  const parsedHash = parseHash(window.location.hash)
  const [end, setEnd] = useState(parsedHash.end != undefined ? new Date(parseInt(parsedHash.end)) : new Date())
  const [start, setStart] = useState(
    parsedHash.start !== undefined ?
      new Date(parseInt(parsedHash.start)) : new Date(end.getTime() - 24 * 60 * 60 * 1000))
  const [measurementType, setMeasurementType] = useState(
    parsedHash.measurementType !== undefined ? parsedHash.measurementType : 'temperature')

  useEffect(() => {
    if (start && end && measurementType) {
      updateHash(start.getTime(), end.getTime(), measurementType)
    }
  }, [start, end, measurementType])
  
  return h('div', null, [
    h(Header, {
      measurementType,
      measurementTypeCallback: setMeasurementType,
      timeCallback: (start, end) => {
      setStart(start)
      setEnd(end)
    }}),
    h(Chart, { start, end, measurementType }),
  ])
}


window.onload = () => render(h(App), document.getElementById('spa'))
