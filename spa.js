import { h, render } from 'https://unpkg.com/preact@latest?module';
import { useState, useEffect } from 'https://unpkg.com/preact@latest/hooks/dist/hooks.module.js?module';
import Dygraph from 'https://unpkg.com/dygraphs@2.1.0?module';


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


const plot = (element, start, end, measurementType) => {
  const startEpoch = Math.floor(start.getTime() / 1000)
  const endEpoch = Math.floor(end.getTime() / 1000)
  fetch('measurements.tsv' +
	`?start=${startEpoch}` +
	`&end=${endEpoch}` +
	`&measurementType=${measurementType}`)
    .then((response) => response.text())
    .then((data) => {
      const periodSecs = endEpoch - startEpoch
      let rollPeriod = 1
      if (periodSecs > 60 * 60) {
	rollPeriod = 5
      } else if (periodSecs > 6 * 60 * 60) {
	rollPeriod = 15
      } else if (periodSecs > 12 * 60 * 60) {
	rollPeriod = 30
      }

      let yLabel
      if (measurementType == 'temperature') {
        yLabel = '°C'
      } else if (measurementType == 'humidity') {
        yLabel = '%'
      } else if (measurementType == 'pressure') {
        yLabel = 'P'
        // yLabel = 'hPa'
        // yValueParser: measurementType == 'pressure' ? (v) => parseFloat(v) / 100 : undefined,
        // baselines: measurementType == 'pressure' ? [{value: 1013.25, label: 'atm'}] : undefined,
      } else if (measurementType == 'battery_voltage') {
        yLabel = 'V'
      } else if (measurementType == 'tx_power') {
        yLabel = 'dBm'
      }

      const g = new Dygraph(
	element,
	data,
	{
          xValueParser: (v) => 1000 * parseInt(v),
	  axes: {
	    x: {
              ticker: Dygraph.dateTicker,
              valueFormatter: Dygraph.dateString_,

              axisLabelFormatter: (d, gran, opts) =>
                Dygraph.dateAxisLabelFormatter(new Date(d), gran, opts)
            },
          },

          legend: 'always',
          animatedZooms: true,
          rollPeriod: rollPeriod,
          ylabel: yLabel
        }
      )
    })
}


const updateHash = (keys) => {
  const hash = serializeHash(keys)
  if (hash != window.location.hash) {
    let hashLess = window.location.href
    if (window.location.href.includes('#')) {
      hashLess = window.location.href.split('#')[0]
    }
    window.history.pushState(null, null, hashLess + hash)
  }
}


const periodToMillis = (period) => {
  const unit = period.charAt(period.length - 1)
  const amount = period.substring(0, period.length - 1)
  if (unit == 'h') {
    return amount * 60 * 60 * 1000
  } else if (unit == 'd') {
    return amount * 24 * 60 * 60 * 1000
  } else {
    throw new Error(`Unknown unit: ${unit}`)
  }
}


const QuickChooser = (props) => {
  const { periodCallback, period } = props
  return h('button', {
    onClick: () => periodCallback(period)
  }, period)
}


const MeasurementTypeDropdown = (props) => {
  const { measurementTypeCallback, measurementType } = props

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
  const { period, periodCallback, measurementType, measurementTypeCallback } = props
  const millisInHour = 60 * 60 * 1000
  return h('div', { className: 'row row-eq-height', style: { marginTop: '25px' }}, [
    h('h3', { className: 'col col-lg-4' }, 'Measurement browser'),
    h('div', { className: 'col align-middle', style: { lineHeight: 2.5 } },
      [h('div', { className: 'float-right'}, 'Show last')]),
    h(QuickChooser, { className: 'col', periodCallback, period: '1h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '3h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '6h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '12h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '24h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '2d' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '3d' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '7d' }),
    h(MeasurementTypeDropdown, { className: 'col', period, measurementType, measurementTypeCallback })
  ])
}


const Chart = (props) => {
  const { start, end, measurementType } = props
  useEffect(() => {
    plot((() => document.getElementById('chart'))(), start, end, measurementType)
  }, [start, end, measurementType])

  return h('div', { id: 'chart', style: {
    position: 'absolute',
    inset: '150px 150px 150px 150px'
  }}, [])
}


const App = (props) => {
  const parsedHash = parseHash(window.location.hash)

  // const [end, setEnd] = useState(parsedHash.end != undefined ? new Date(parseInt(parsedHash.end)) : new Date())
  // const [start, setStart] = useState(
  //   parsedHash.start !== undefined ?
  //     new Date(parseInt(parsedHash.start)) : new Date(end.getTime() - 24 * 60 * 60 * 1000))

  const [period, setPeriod] = useState(parsedHash.period !== undefined ? parsedHash.period : '24h')

  const [measurementType, setMeasurementType] = useState(
    parsedHash.measurementType !== undefined ? parsedHash.measurementType : 'temperature')

  // useEffect(() => {
  //   if (start && end && measurementType) {
  //     updateHash({ start: start.getTime(), end: end.getTime(), measurementType})
  //   }
  // }, [start, end, measurementType])

  useEffect(() => {
    if (period) {
      updateHash({ period, measurementType })
    }
  }, [period, measurementType])

  const now = new Date()
  return h('div', null, [
    h(Header, {
      measurementType,
      measurementTypeCallback: setMeasurementType,
      // timeCallback: (start, end) => {
      // 	setStart(start)
      // 	setEnd(end)
      // }
      period,
      periodCallback: (period) => {
	setPeriod(period)
      }
    }),
    h(Chart, { start: new Date(now - periodToMillis(period)), end: now, measurementType }),
  ])
}


window.onload = () => render(h(App), document.getElementById('spa'))
