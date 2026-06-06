import { Composition } from "remotion";
import { TestRed } from "./TestRed";
export const TestRoot = () => <Composition id="Test" component={TestRed} durationInFrames={10} fps={30} width={1920} height={1080} />;
